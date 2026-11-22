# Chuyển một thành phần javax sang jakarta đúng phạm vi

Một trong những lỗi phổ biến khi nâng cấp ứng dụng Java EE là dùng thao tác tìm–thay toàn dự án: đổi tất cả chuỗi `javax.` thành `jakarta.`. Việc này có thể phá hỏng những API **vẫn thuộc Java SE** như `javax.sql.DataSource`, `javax.crypto.Cipher`, `javax.naming.InitialContext`, `javax.net.ssl.SSLContext` hay `javax.tools.JavaCompiler`. Ngược lại, nếu chỉ đổi import trong một class mà chưa nâng API dependency, Servlet container hoặc thư viện thực thi, ứng dụng có thể build được nhưng thất bại ngay lúc khởi động với `NoClassDefFoundError`.

Bài thực hành này hướng dẫn chuyển **đúng một thành phần có ranh giới rõ ràng**: `RequestIdFilter`, một Servlet filter gắn mã định danh yêu cầu cho các endpoint `/api/*`. Bản cũ dùng `javax.servlet.*`; bản mới dùng `jakarta.servlet.*`. Chúng ta sẽ chốt phạm vi, bảo toàn hợp đồng đầu vào/đầu ra, thay code và dependency tương ứng, viết JUnit/Mockito tests, đóng gói WAR và kiểm tra trên container mục tiêu. Mẫu áp dụng được cho nhiều migration Java EE → Jakarta nhưng **không có nghĩa mọi thành phần Java EE phải nâng đồng thời theo cùng cách**.

## 1. Mục tiêu học tập

Sau bài thực hành, bạn có thể:

1. Xác định một API `javax.*` có thuộc nhóm Java/Jakarta EE cần đổi namespace hay không.
2. Chỉ ra ranh giới một thành phần và các dependency trực tiếp, không sửa lan sang phần không liên quan.
3. Đặt phiên bản Jakarta Servlet API, JDK và Servlet container phù hợp.
4. Chuyển chữ ký `Filter`, `ServletRequest`, `ServletResponse`, `FilterChain` và `ServletException` đúng namespace.
5. Giữ nguyên hành vi: request được tiếp tục qua filter chain đúng một lần, có request ID và response header nhất quán.
6. Viết test xác nhận cả đường thành công và đường lỗi.
7. Đóng gói đúng Maven scope `provided` cho WAR chạy trên container có API Jakarta.
8. Chẩn đoán lỗi trộn `javax.servlet`/`jakarta.servlet` hoặc load sai artifact.
9. Biết khi nào cần nâng toàn bộ runtime boundary và khi nào nên cô lập thành phần cũ bằng một adapter qua giao thức.
10. Ghi nhận bằng chứng và rollback phù hợp trước khi áp dụng trong hệ thống thật.

## 2. Bối cảnh bài thực hành

Giả sử hệ thống có một WAR legacy triển khai trên **Apache Tomcat 9**, sử dụng Java 8 hoặc một JDK được Tomcat 9 hỗ trợ và Servlet API thuộc namespace `javax.servlet.*`. Trong WAR có filter:

```text
HTTP request
     |
     v
RequestIdFilter (javax.servlet.Filter)
     |
     v
Các filter khác / Servlet / Controller
     |
     v
HTTP response có X-Request-ID
```

Mục tiêu của bài thực hành là chuyển filter và môi trường WAR thử nghiệm sang:

| Thành phần | Trước | Sau |
|---|---|---|
| JDK dùng build | Java 8 trong tình huống ban đầu | Java 17 |
| API | Java EE Servlet, `javax.servlet.*` | Jakarta Servlet 6.0, `jakarta.servlet.*` |
| Container | Tomcat 9.x | Tomcat 10.1.x |
| Đóng gói | WAR | WAR |
| Logic nghiệp vụ | Sinh request ID và tiếp tục filter chain | Giữ nguyên |
| URL áp dụng | `/api/*` | Giữ nguyên trong phạm vi webapp |
| HTTP response | `X-Request-ID` | Giữ nguyên |
| Java SE packages | Giữ nguyên | Giữ nguyên |

**Quan trọng:** Tomcat 10.1 hỗ trợ Jakarta Servlet 6.0 và yêu cầu Java 11 trở lên; ở bài này ta chọn Java 17 để có baseline cụ thể. Tomcat 10.0 thuộc thế hệ Servlet 5.0, còn Tomcat 9 dùng namespace `javax.servlet.*`. Không chọn phiên bản API/container tùy tiện theo số major.

Để làm workshop dễ tái hiện, chúng ta tạo một **WAR thử nghiệm tối thiểu** chỉ có filter và một servlet `/api/ping`. Servlet `PingServlet` chỉ là fixture xác minh đường HTTP; **thành phần chính được migration là `RequestIdFilter`**. Trong hệ thống thật, các thành phần nằm trên cùng servlet runtime cũng phải tương thích Jakarta; bài học không khuyến khích đặt filter mới vào một WAR đang chạy trên Tomcat 9.

## 3. “Đúng phạm vi” có nghĩa là gì?

Có ba phạm vi cần tách bạch:

- **Phạm vi sửa code:** một filter và những import/chữ ký type liên quan.
- **Phạm vi runtime bắt buộc đồng bộ:** Servlet API và container/Jakarta-compatible framework mà filter được triển khai vào.
- **Phạm vi ngoài bài:** các module khác không phụ thuộc filter, business domain, database schema, Java SE `javax.*` packages, API clients không liên quan.

Một kế hoạch chuyển đổi có thể giới hạn code change trong một class, nhưng **không thể** giữ container runtime `javax.servlet.Filter` và hy vọng nó nhận một object implement `jakarta.servlet.Filter`: đó là hai interface khác nhau về Java type identity.

### 3.1. Ranh giới dependency cần vẽ

```text
                                Java SE API
                     java.util.UUID, java.io.IOException
                                  |
                                  v
                    +---------------------------+
HTTP /api/* ------> | RequestIdFilter           |
                    | jakarta.servlet.Filter    |
                    +---------------------------+
                         |                 |
                         v                 v
             jakarta.servlet-api      Servlet container
                   6.0.0               Tomcat 10.1.x
                         |
                         v
                  /api/ping fixture
```

Logic tạo UUID trong `java.util` không cần migration namespace. Điều cần đổi là Servlet-facing interface và type signatures; đi kèm với API/container thực thi.

## 4. Phân loại javax trước khi sửa

Một tập import legacy có thể gồm:

```java
import javax.servlet.Filter;
import javax.servlet.ServletException;
import javax.sql.DataSource;
import javax.crypto.Cipher;
import javax.naming.InitialContext;
import javax.net.ssl.SSLContext;
import javax.xml.parsers.DocumentBuilderFactory;
```

**Không** được thay tất cả thành `jakarta.*`. Phân loại:

| Import cũ | Quyết định | Lý do |
|---|---|---|
| `javax.servlet.Filter` | Đổi sang `jakarta.servlet.Filter` | Servlet là Jakarta EE API sau namespace migration. |
| `javax.servlet.FilterChain` | Đổi sang `jakarta.servlet.FilterChain` | Phải dùng cùng Servlet API family. |
| `javax.servlet.ServletRequest` | Đổi sang `jakarta.servlet.ServletRequest` | Type của chữ ký Servlet filter mới. |
| `javax.servlet.ServletResponse` | Đổi sang `jakarta.servlet.ServletResponse` | Type của chữ ký filter mới. |
| `javax.servlet.ServletException` | Đổi sang `jakarta.servlet.ServletException` | Exception API tương ứng. |
| `javax.servlet.http.HttpServletResponse` | Đổi sang `jakarta.servlet.http.HttpServletResponse` | HTTP Servlet API mới. |
| `javax.annotation.PostConstruct` | Đánh giá chuyển `jakarta.annotation.PostConstruct` nếu đang dùng Jakarta Annotations | Không đổi nếu đó là API khác hoặc code ngoài phạm vi. |
| `javax.persistence.Entity` | Chỉ đổi khi đang nâng JPA/Jakarta Persistence layer | Không liên quan trực tiếp filter. |
| `javax.validation.Valid` | Chỉ đổi khi nâng Bean Validation/Jakarta Validation stack | Không thuộc Java SE nhưng cần quyết định theo module. |
| `javax.sql.DataSource` | **Giữ nguyên** | Java SE JDBC API. |
| `javax.crypto.Cipher` | **Giữ nguyên** | Java SE cryptography API. |
| `javax.naming.InitialContext` | **Giữ nguyên** | Java SE JNDI API. |
| `javax.net.ssl.SSLContext` | **Giữ nguyên** | Java SE TLS API. |
| `javax.xml.parsers.DocumentBuilderFactory` | **Giữ nguyên** | Java SE XML/JAXP API. |
| `javax.tools.JavaCompiler` | **Giữ nguyên** | Java SE compiler API. |

Đây là trọng tâm của yêu cầu “đúng phạm vi”: chỉ đổi API có **chủ sở hữu và phiên bản namespace xác định**, không căn cứ vào tiền tố `javax` đơn thuần.

## 5. Kiểm kê trước migration

Trong dự án thực tế, lập danh sách:
- Những file thực sự import `javax.servlet.*`.
- Class nào `implements Filter`, `extends HttpServlet`, hoặc implement `ServletRequestListener`.
- Cấu hình `web.xml`, `@WebFilter`, `@WebServlet`, programmatic filter registrations.
- WAR đang chạy trên Tomcat phiên bản nào.
- Servlet API dependency được khai báo ở Maven/Gradle scope nào.
- Thư viện bên thứ ba dùng Servlet Filter như security filters, tracing, compression, CORS.
- Filter order, URL mapping, async/dispatcher types.
- Client-visible behavior: response headers, error paths, encoding, status.
- Các Java SE imports `javax.*` phải giữ nguyên.

Ví dụ lệnh tìm chuỗi (minh họa cho mã nguồn trong workspace):

```bash
grep -R "javax\.servlet" src/
grep -R "jakarta\.servlet" src/
grep -R "RequestIdFilter" src/
```

Trên PowerShell, có thể dùng:

```powershell
Get-ChildItem -Recurse -File src |
  Select-String -Pattern 'javax\.servlet','jakarta\.servlet','RequestIdFilter'
```

Kết quả search không phải danh sách thay thế tự động: phải đọc type/annotation nào đang được sử dụng và nơi nó được nạp lúc runtime.

## 6. Xác nhận hợp đồng trước khi chỉnh sửa

Với `RequestIdFilter`, định nghĩa đầu ra dự kiến:

| Điều kiện | Hành vi |
|---|---|
| Request khớp `/api/*` | Filter được gọi đúng một lần theo mapping/dispatch được khai báo. |
| Request đến filter | Tạo một UUID string không dựa vào input thiếu tin cậy. |
| Trong downstream code | Attribute `requestId` chứa cùng UUID. |
| HTTP response | Header `X-Request-ID` chứa cùng UUID. |
| Downstream thành công | Filter gọi `chain.doFilter(...)` đúng một lần. |
| Downstream ném `ServletException` hoặc `IOException` | Không nuốt exception hoặc thay đổi status trái hợp đồng. |
| URL ngoài `/api/*` | Không được filter chèn header nếu không có mapping khác. |
| Dispatcher type | Chỉ REQUEST trong ví dụ; ERROR/FORWARD/ASYNC phải quyết định riêng nếu ứng dụng cần. |

Bộ hợp đồng này đủ để phát hiện migration làm đổi hành vi dù code đã compile. Nếu trong dự án thật request ID được lấy từ upstream proxy, hãy thêm chính sách xác thực/chuẩn hóa input cụ thể thay vì chấp nhận tùy ý header do client gửi.

## 7. Code trước chuyển đổi: javax Servlet Filter

File legacy `src/main/java/com/example/web/RequestIdFilter.java`:

```java
package com.example.web;

import java.io.IOException;
import java.util.UUID;

import javax.servlet.DispatcherType;
import javax.servlet.Filter;
import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.ServletRequest;
import javax.servlet.ServletResponse;
import javax.servlet.annotation.WebFilter;
import javax.servlet.http.HttpServletResponse;

@WebFilter(
    urlPatterns = "/api/*",
    dispatcherTypes = {DispatcherType.REQUEST}
)
public final class RequestIdFilter implements Filter {

    public static final String ATTRIBUTE = "requestId";
    public static final String HEADER = "X-Request-ID";

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        String id = UUID.randomUUID().toString();
        request.setAttribute(ATTRIBUTE, id);

        if (response instanceof HttpServletResponse) {
            ((HttpServletResponse) response).setHeader(HEADER, id);
        }

        chain.doFilter(request, response);
    }
}
```

Đây là cách viết tương thích với Java 8 ở cấp cú pháp. Logic:
1. Sinh UUID.
2. Lưu request attribute.
3. Đặt HTTP response header.
4. Gọi chain đúng một lần.
5. Để downstream exceptions đi lên theo contract.

Lỗi dễ gặp khi nâng: developer đổi vài import đầu nhưng quên `ServletException`, `FilterChain` hoặc `@WebFilter` thuộc cùng namespace. Cần đổi **toàn bộ type thuộc Servlet API** của thành phần, không chỉ interface `Filter`.

## 8. Chuẩn bị Maven project thử nghiệm

Tạo một Maven WAR project với cấu trúc tối thiểu:

```text
request-id-demo/
├── pom.xml
├── src/
│   ├── main/
│   │   └── java/com/example/web/
│   │       ├── RequestIdFilter.java
│   │       └── PingServlet.java
│   └── test/
│       └── java/com/example/web/
│           └── RequestIdFilterTest.java
└── target/                 (sinh bởi Maven)
```

**Không đưa hai version của `RequestIdFilter` vào cùng source set.** Bản legacy ở mục trên chỉ để so sánh. Trong project target chỉ giữ mã Jakarta mới.

File `pom.xml` minh họa phiên bản Jakarta Servlet 6.0, Java 17 và JUnit 5/Mockito. Các plugin/test dependency version là bộ ví dụ có thể tái hiện khi được giải quyết từ repository phù hợp, **không được coi là khuyến nghị phiên bản mới nhất tại mọi thời điểm**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>request-id-demo</artifactId>
    <version>1.0.0</version>
    <packaging>war</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.version>5.11.4</junit.version>
        <mockito.version>5.15.2</mockito.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>jakarta.servlet</groupId>
            <artifactId>jakarta.servlet-api</artifactId>
            <version>6.0.0</version>
            <scope>provided</scope>
        </dependency>

        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>org.mockito</groupId>
            <artifactId>mockito-core</artifactId>
            <version>${mockito.version}</version>
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
                <version>3.4.0</version>
                <configuration>
                    <failOnMissingWebXml>false</failOnMissingWebXml>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tại sao `provided`?

- Maven dùng Jakarta Servlet API để **biên dịch** và **chạy unit tests**.
- Tomcat 10.1 cung cấp Servlet implementation/API ở runtime.
- WAR không nên tự đóng gói một bản Servlet API khác vào `WEB-INF/lib/` khi container là bên cung cấp.

Trong một ứng dụng **embedded server** hay executable JAR, cách quản lý dependencies có thể khác; ở bài này intentionally chọn WAR external container để minh họa rõ.

## 9. Kiểm tra JDK Maven thực dùng

Trước khi biên dịch trong môi trường học tập:

```bash
java -version
javac -version
mvn -version
```

Kỳ vọng: Maven được chạy trên JDK phù hợp với Java 17 toolchain. Có nhiều installation trên máy, `mvn -version` có thể khác `java -version` ở shell. Nếu dự án dùng Maven Toolchains, kiểm tra cấu hình chọn compiler thực tế.

Đừng cố dùng `-source 8 -target 8` với mã tận dụng syntax Java 17. Trong ví dụ đích, `maven.compiler.release=17` mô tả source, bytecode và Java SE API target ở mức compiler được dùng.

Khi làm việc trong hệ thống thật, có thể chọn lower release nếu framework/container hỗ trợ và business yêu cầu. Java 17 là một baseline minh họa, không phải yêu cầu cố định của mọi Jakarta Servlet application.

## 10. Code sau chuyển đổi: jakarta Servlet Filter

Thay file `src/main/java/com/example/web/RequestIdFilter.java` bằng:

```java
package com.example.web;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.annotation.WebFilter;
import jakarta.servlet.http.HttpServletResponse;

@WebFilter(
    urlPatterns = "/api/*",
    dispatcherTypes = {DispatcherType.REQUEST}
)
public final class RequestIdFilter implements Filter {

    public static final String ATTRIBUTE = "requestId";
    public static final String HEADER = "X-Request-ID";

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        String id = UUID.randomUUID().toString();
        request.setAttribute(ATTRIBUTE, id);

        if (response instanceof HttpServletResponse httpResponse) {
            httpResponse.setHeader(HEADER, id);
        }

        chain.doFilter(request, response);
    }
}
```

Những thay đổi chính:
- `javax.servlet.*` → `jakarta.servlet.*`.
- `javax.servlet.annotation.WebFilter` → `jakarta.servlet.annotation.WebFilter`.
- `javax.servlet.http.HttpServletResponse` → `jakarta.servlet.http.HttpServletResponse`.
- Giữ nguyên `java.io.IOException` và `java.util.UUID`.
- Phần `instanceof` dùng pattern matching hợp lệ ở Java 17, nhưng có thể giữ cách cast cũ nếu muốn giảm số thay đổi cú pháp.

**Về hành vi:** không đổi response header, request attribute, URL mapping hoặc cơ chế chuyển tiếp downstream. Đây là migration về **type namespace và runtime contract**, không phải thay logic nghiệp vụ.

## 11. Fixture endpoint để kiểm tra request thật

Thêm file `src/main/java/com/example/web/PingServlet.java`:

```java
package com.example.web;

import java.io.IOException;

import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

@WebServlet("/api/ping")
public final class PingServlet extends HttpServlet {

    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response)
            throws IOException {

        Object requestId =
                request.getAttribute(RequestIdFilter.ATTRIBUTE);

        response.setContentType("text/plain");
        response.setCharacterEncoding("UTF-8");

        response.getWriter().println(
                "pong; requestId=" + requestId);
    }
}
```

`PingServlet` chỉ có vai trò làm fixture test HTTP, không đại diện cho việc phải chuyển toàn bộ controllers trong dự án thật. Vì fixture chạy **cùng Jakarta Servlet container** nên cũng phải dùng `jakarta.servlet.http.*`. Điều này minh họa sự khác biệt giữa **phạm vi code chủ động sửa** (filter) và **các type của runtime boundary** phải đồng bộ để test có nghĩa.

Response mong đợi:

```text
HTTP/1.1 200
X-Request-ID: 0b7f... (UUID)

pong; requestId=0b7f... (cùng giá trị)
```

UUID chỉ minh họa và thay đổi theo từng request.

## 12. Vì sao annotation và URL mapping cũng nằm trong phạm vi?

Thành phần Servlet không chỉ là một interface Java. Container có thể tìm:
- `@WebFilter`.
- `web.xml` filter/filter-mapping.
- Programmatic `ServletContext.addFilter`.
- Framework-specific filter registration.
- `@WebListener` hoặc ServletContainerInitializer trong một số kiến trúc.

Nếu đổi implementation sang `jakarta.servlet.Filter` nhưng giữ metadata `javax.servlet.annotation.WebFilter` trong artifact cũ, container Jakarta có thể không đăng ký filter theo cách dự kiến. Nếu cả annotation và web.xml cùng đăng ký, filter có nguy cơ được gọi nhiều lần hoặc thứ tự khác.

Ở bài này, dùng **chỉ `@WebFilter`** và không khai báo filter tương tự trong `web.xml`. Với ứng dụng thật, phải kiểm tra thứ tự, dispatcher types, async support và phương thức registration đang tồn tại; đừng chuyển đổi tùy tiện thành annotation nếu cần bảo toàn order đặc thù.

### 12.1. Context path không nằm trong filter URL pattern

Giả sử WAR được deploy thành context:

```text
/request-id-demo
```

HTTP URL:

```text
http://localhost:8080/request-id-demo/api/ping
```

`@WebFilter(urlPatterns = "/api/*")` được khai báo **trong phạm vi webapp**, không phải `/request-id-demo/api/*`. Lẫn context path và servlet mapping có thể khiến filter không chạy như kỳ vọng.
## 13. Unit test JUnit/Mockito: giữ nguyên contract

Trong bài thực hành, mục tiêu quan trọng nhất không phải thấy chữ `jakarta` trong import, mà là xác nhận filter còn hoạt động đúng. Vì vậy, kiểm thử sử dụng chính **Jakarta Servlet interfaces** trên test classpath.

File `src/test/java/com/example/web/RequestIdFilterTest.java`:

```java
package com.example.web;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class RequestIdFilterTest {

    @Test
    void shouldSetRequestIdAndContinueOnce() throws Exception {
        HttpServletRequest request =
                mock(HttpServletRequest.class);
        HttpServletResponse response =
                mock(HttpServletResponse.class);
        FilterChain chain = mock(FilterChain.class);

        RequestIdFilter filter = new RequestIdFilter();
        filter.doFilter(request, response, chain);

        ArgumentCaptor<String> idCaptor =
                ArgumentCaptor.forClass(String.class);

        verify(request).setAttribute(
                eq(RequestIdFilter.ATTRIBUTE),
                idCaptor.capture());

        String id = idCaptor.getValue();
        assertDoesNotThrow(() -> UUID.fromString(id));

        verify(response).setHeader(
                RequestIdFilter.HEADER, id);

        verify(chain, times(1)).doFilter(request, response);
    }

    @Test
    void shouldPropagateServletException() throws Exception {
        ServletRequest request = mock(ServletRequest.class);
        ServletResponse response = mock(ServletResponse.class);
        FilterChain chain = mock(FilterChain.class);

        ServletException failure =
                new ServletException("downstream failed");

        doThrow(failure).when(chain)
                .doFilter(request, response);

        ServletException actual = assertThrows(
                ServletException.class,
                () -> new RequestIdFilter().doFilter(
                        request, response, chain));

        assertEquals("downstream failed", actual.getMessage());
        verify(chain, times(1)).doFilter(request, response);
    }

    @Test
    void shouldPropagateIOException() throws Exception {
        ServletRequest request = mock(ServletRequest.class);
        HttpServletResponse response =
                mock(HttpServletResponse.class);
        FilterChain chain = mock(FilterChain.class);

        doThrow(new IOException("output failed")).when(chain)
                .doFilter(request, response);

        IOException actual = assertThrows(
                IOException.class,
                () -> new RequestIdFilter().doFilter(
                        request, response, chain));

        assertEquals("output failed", actual.getMessage());
        verify(chain, times(1)).doFilter(request, response);
    }

    @Test
    void shouldHandleNonHttpServletResponse() throws Exception {
        ServletRequest request = mock(ServletRequest.class);
        ServletResponse response = mock(ServletResponse.class);
        FilterChain chain = mock(FilterChain.class);

        new RequestIdFilter().doFilter(request, response, chain);

        verify(chain, times(1)).doFilter(request, response);
    }
}
```

### 13.1. Những điều test này xác nhận

- **Type compatibility ở compile time:** test và filter đều dùng `jakarta.servlet.*`.
- **Attribute và header khớp:** request ID do filter tạo là UUID parse được, cùng giá trị truyền vào downstream và HTTP header.
- **Filter không chặn request:** `chain.doFilter` được gọi đúng một lần.
- **Exception propagation:** không nuốt `ServletException` hoặc `IOException` của downstream.
- **Non-HTTP response:** filter không cast mù quáng `ServletResponse` sang HTTP response.

Lưu ý Mockito là library mock; unit tests **không chứng minh** container thực sự tìm annotation, mapping `/api/*`, thứ tự filters hoặc API/runtime classloader. Đó là lý do cần bước triển khai WAR trên container thật.

### 13.2. Vì sao kiểm thử “cùng value” quan trọng hơn test từng lệnh rời?

Một implementation lỗi có thể tạo hai UUID:

```java
request.setAttribute("requestId",
        UUID.randomUUID().toString());

httpResponse.setHeader("X-Request-ID",
        UUID.randomUUID().toString());
```

Khi đó test riêng “header có được set” vẫn xanh, nhưng request attribute và header không tương ứng, làm tracing mất giá trị. Kiểm thử dùng `ArgumentCaptor` để đối chiếu **một giá trị được bảo toàn qua boundary**, đúng với mục tiêu contract.

## 14. Kiểm thử type identity một cách tường minh

Có thể bổ sung một test nhỏ:

```java
package com.example.web;

import static org.junit.jupiter.api.Assertions.assertTrue;
import jakarta.servlet.Filter;
import org.junit.jupiter.api.Test;

class ServletNamespaceTest {

    @Test
    void filterImplementsJakartaContract() {
        assertTrue(Filter.class.isAssignableFrom(
                RequestIdFilter.class));
    }
}
```

Test này chứng minh class implementation tương thích với `jakarta.servlet.Filter` **trong test classpath đã chọn**. Nó không thay thế việc kiểm tra server runtime: class Jakarta API vẫn có thể vắng mặt trong một Tomcat 9 container hoặc bị nạp từ classloader không phù hợp.

### 14.1. Không có adapter cast tự động giữa hai Filter

Dù hai interface có các method rất giống nhau:

```text
javax.servlet.Filter
        ≠
jakarta.servlet.Filter
```

Một object implement `javax.servlet.Filter` không thể tự cast sang `jakarta.servlet.Filter`. Đừng viết:

```java
jakarta.servlet.Filter newFilter =
        (jakarta.servlet.Filter) oldJavaxFilter;
```

Nếu `oldJavaxFilter` không thực sự implement Jakarta Filter, cast không trở nên hợp lệ nhờ thêm cả hai API JAR. Với binary legacy không thể biên dịch lại, phải xem xét transformation tool được hỗ trợ hoặc cô lập một adapter ở **ranh giới khác**, thay vì dùng ép kiểu không tương thích.

## 15. Biên dịch, chạy unit tests và tạo WAR

Trong thư mục `request-id-demo/`, trên máy có Maven và JDK thích hợp:

```bash
mvn clean test
mvn package
```

Hoặc chạy full lifecycle mục tiêu:

```bash
mvn clean verify
```

Đây là **lệnh người học có thể thực hiện trong project thực hành**; nội dung bài học không khẳng định các lệnh đã được chạy.

Với POM ở mục 8, file sản phẩm dự kiến:

```text
target/request-id-demo-1.0.0.war
```

Đọc kết quả build:
- Java sources biên dịch không còn phụ thuộc `javax.servlet.*`.
- Unit tests chạy với `jakarta.servlet-api` trong test/compile classpath.
- Build tạo WAR, không chỉ JAR thông thường.
- Nếu build chạy bằng JDK không hỗ trợ `--release 17`, điều chỉnh đúng toolchain chứ không sửa API tùy tiện.
- Một warning thuộc plugin khác phải được phân loại, không tự thêm JAR cũ như `javax.servlet-api` để lấp lỗi.

## 16. Kiểm tra thành phần trong WAR

Dùng:

```bash
jar tf target/request-id-demo-1.0.0.war
```

Các entry thường có:

```text
META-INF/
WEB-INF/
WEB-INF/classes/
WEB-INF/classes/com/example/web/RequestIdFilter.class
WEB-INF/classes/com/example/web/PingServlet.class
...
```

Không nên thấy file `WEB-INF/lib/jakarta.servlet-api-6.0.0.jar` trong WAR với dependency `provided` ở POM này, vì container cung cấp API. Tuy nhiên, WAR plugin có thể đưa các test/other dependencies sai scope nếu cấu hình project khác; cần xác nhận artifact thực tế.

Nếu thấy `javax.servlet-api` được đóng gói kèm trong `WEB-INF/lib/`, đừng kết luận chỉ cần xóa JAR là xong. Phải điều tra dependency nào kéo nó vào, class trong application hoặc framework nào vẫn yêu cầu namespace cũ.

### 16.1. Kiểm tra bytecode signature khi cần

Ví dụ:

```bash
javap -classpath target/classes \
  com.example.web.RequestIdFilter
```

Output khái niệm:

```text
public final class com.example.web.RequestIdFilter
    implements jakarta.servlet.Filter {
  ...
}
```

Nếu output vẫn cho thấy `javax.servlet.Filter`, có thể bạn đang kiểm tra artifact cũ hoặc source cũ còn được compile. Hãy chạy clean build, kiểm tra commit/hash và đường dẫn artifact.

`javap` cho thấy bytecode signature nhưng không bảo đảm container đúng thế hệ đang được triển khai. Hai yếu tố cần xác minh riêng.

## 17. Triển khai trên Tomcat phù hợp

Với ví dụ mục tiêu, dùng **Tomcat 10.1.x** có Java runtime đáp ứng yêu cầu và một version được duy trì/vá bảo mật phù hợp. Lưu ý số liệu `10.1.x` biểu thị nhánh container; cần chọn patch release cụ thể đang được hỗ trợ, không chỉ ghi “Tomcat 10”.

Một quy trình thủ công:
1. Khởi động Tomcat 10.1 với JDK 17 đã chọn.
2. Sao chép file `request-id-demo-1.0.0.war` vào thư mục deploy của Tomcat theo môi trường triển khai.
3. Đảm bảo annotation scanning được bật trong phạm vi webapp.
4. Kiểm tra WAR triển khai thành công, không có lỗi `ClassNotFoundException`/`NoClassDefFoundError`.
5. Gọi endpoint `/request-id-demo/api/ping` qua cổng cấu hình.

Ví dụ:

```bash
curl -i http://localhost:8080/request-id-demo/api/ping
```

Phản hồi minh họa:

```text
HTTP/1.1 200
Content-Type: text/plain;charset=UTF-8
X-Request-ID: 1e57197c-ef33-41c1-91b3-0c4c3a141800

pong; requestId=1e57197c-ef33-41c1-91b3-0c4c3a141800
```

Giá trị UUID là ví dụ. Tên header HTTP không phân biệt hoa thường. Nếu context path trong Tomcat khác tên WAR, phải thay URL; không hardcode `/request-id-demo` trong source filter.

### 17.1. Kiểm tra filter không áp nhầm ngoài phạm vi

Thử một đường ngoài `/api/*`, ví dụ:

```bash
curl -i http://localhost:8080/request-id-demo/not-api
```

Trong WAR tối thiểu, endpoint này có thể trả HTTP 404. Filter `RequestIdFilter` không nên được gọi chỉ vì có request tới cùng webapp. Tuy nhiên, các filter hoặc reverse proxy **khác** có thể vẫn thêm header request ID, nên việc chỉ thấy header trên một môi trường sản xuất không chứng minh filter cụ thể đã chạy.

Trong integration tests thực tế, nên dùng filter invocation counter được kiểm soát hoặc endpoint fixture để xác minh mapping rõ ràng; không suy từ một header duy nhất nếu có nhiều nguồn cùng thêm header đó.

## 18. Deployment WAR với Spring Boot khác thế nào?

Nếu dự án dùng Spring Boot 3.x trên Servlet stack, Spring Framework 6 và Jakarta Servlet APIs đã thuộc cùng hệ sinh thái. Nhưng cấu hình khác với WAR thuần:

- Có thể có embedded Tomcat hoặc external Servlet container.
- Cách đăng ký filters có thể thông qua `FilterRegistrationBean`, `@Component` hoặc Servlet annotation scanning tùy cấu hình.
- Spring Security có `SecurityFilterChain` riêng; custom servlet filters phải được đăng ký đúng mục đích và thứ tự.
- Một filter bean bị cả container auto-registration và Security chain register có thể chạy hai lần.

Mẫu tối giản kiểu Spring configuration (chỉ minh họa khi dùng Servlet-based Spring Boot):

```java
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class FilterConfig {

    @Bean
    FilterRegistrationBean<RequestIdFilter> requestIdRegistration() {
        FilterRegistrationBean<RequestIdFilter> registration =
                new FilterRegistrationBean<>();

        registration.setFilter(new RequestIdFilter());
        registration.addUrlPatterns("/api/*");
        registration.setName("requestIdFilter");
        return registration;
    }
}
```

Nếu dùng cách registration này, **không nên đồng thời giữ một registration tự động tương đương bằng `@WebFilter`** trong một môi trường có scan annotations trừ khi bạn hiểu rõ cách framework/container phối hợp và đã kiểm chứng không chạy trùng. Với Spring Boot hiện đại, nên đối chiếu phiên bản Boot/Spring để dùng đúng package và cấu hình API.

Trong bài chính, ta dùng WAR thuần với `@WebFilter`. Đoạn Spring này chỉ giúp nhận diện cách chuyển cùng component khi đích là một framework khác; **không áp nó cùng lúc lên project WAR mẫu**.

## 19. Khi runtime dùng Tomcat 9 sẽ xảy ra gì?

Một WAR với `RequestIdFilter implements jakarta.servlet.Filter` triển khai lên Tomcat 9, vốn dùng `javax.servlet.Filter`, **không tương thích như đã kỳ vọng**.

Những kết quả có thể gặp:
- Container không nhận class như một Servlet Filter hợp lệ.
- Lỗi nạp `jakarta.servlet.Filter` hoặc lớp annotation tương ứng.
- `NoClassDefFoundError: jakarta/servlet/Filter`.
- Class có mặt nhờ một API JAR tự thêm nhưng không được Tomcat 9 xử lý như filter đúng type.
- Deployment thất bại hoặc filter bị bỏ qua, gây sai contract dù endpoint khác vẫn trả response.

Không chữa bằng cách đặt cả `javax.servlet-api` và `jakarta.servlet-api` vào `WEB-INF/lib`. Điều đó **không chuyển** type identity của các interfaces và có thể tạo thêm xung đột loader.

Một runtime boundary thường phải nâng **cùng nhóm**: Servlet container, Spring/Jakarta framework integration, filters/listeners/servlets, và API dependency. Đó là phần bắt buộc để một thay đổi nhỏ về code thực sự chạy đúng.

## 20. Lỗi thường gặp khi chuyển namespace nửa vời

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| `package jakarta.servlet does not exist` | Thiếu Jakarta API trên compile classpath. | Khai báo đúng Jakarta Servlet API version/scope. |
| `RequestIdFilter is not abstract and does not override ...` | Interface và method signature đến từ hai namespace khác nhau. | Đổi toàn bộ Servlet type imports/chữ ký. |
| `NoClassDefFoundError: jakarta/servlet/Filter` | Runtime container/JAR không có Jakarta API. | Chọn Servlet container target tương ứng. |
| `NoClassDefFoundError: javax/servlet/Filter` | Thư viện cũ vẫn liên kết với javax API. | Nâng/thay thư viện, không chỉ thêm Jakarta JAR. |
| `ClassCastException` giữa javax/jakarta Filter | Hai interface là hai type khác nhau. | Recompile/migrate component hoặc cô lập boundary. |
| Filter không chạy nhưng endpoint trả 200 | Annotation/config registration sai, metadata scanning disabled. | Kiểm tra filter mapping, registration và container logs. |
| Filter chạy hai lần | Hai cơ chế đăng ký, hoặc nhiều filter instances. | Chỉ giữ một đường registration có chủ đích. |
| Endpoint ngoài `/api/*` cũng có header | Filter khác/proxy hoặc mapping rộng. | Truy vết header source, xem mappings/order. |
| POST/async/error có hành vi khác | Dispatcher types/async support không được giữ. | Bảo toàn config gốc và test các dispatch paths. |
| Đúng ở test nhưng sai trên server | Test classpath khác runtime/container. | Deploy WAR lên container target thực. |
| `javax.sql.DataSource` bị đổi thành `jakarta.sql` | Bulk replace sai phạm vi. | Giữ nguyên Java SE import. |

Chú ý `NoClassDefFoundError` và `ClassNotFoundException` có thể là **triệu chứng** của việc trộn thế hệ Servlet hoặc package sai, không phải bằng chứng phải thêm JAR ngẫu nhiên.

## 21. Test matrix trước/sau phải phản ánh contract

| Test | Trước (Tomcat 9 + javax) | Sau (Tomcat 10.1 + jakarta) |
|---|---|---|
| `GET /api/ping` | HTTP 200 | HTTP 200 |
| `X-Request-ID` | Có UUID | Có UUID |
| Request attribute | Trùng header | Trùng header |
| Chain execution | Đúng một lần | Đúng một lần |
| `/not-api` | Filter không áp | Filter không áp |
| `ServletException` downstream | Không bị nuốt | Không bị nuốt |
| `IOException` downstream | Không bị nuốt | Không bị nuốt |
| Dispatcher REQUEST | Khớp | Khớp |
| Dispatcher ERROR/ASYNC | Theo config cũ | Không vô tình thay đổi |
| JVM/container startup | Không linkage errors | Không linkage errors |
| WAR API dependency | Container cung cấp đúng javax API | Container cung cấp đúng Jakarta API |
| Java SE `javax.*` | Giữ nguyên | Giữ nguyên |

Trong thực tế, không nhất thiết mọi test cũ chạy nguyên văn với cả hai container nếu test dependencies khác nhau. Điều cần giữ là **đầu ra hợp đồng**, không phải cố trộn Java types của hai thế hệ trong cùng test classpath.

## 22. Thứ tự migrate nếu dự án có nhiều thư viện web

Chuyển một filter độc lập là tình huống đơn giản nhất. Một WAR thật có thể phụ thuộc:
- Servlet container.
- Spring MVC/Security.
- REST/JAX-RS implementation.
- CDI/Bean Validation.
- Logging/metrics filter.
- CORS/authentication filters.
- Third-party agents/interceptors.
- Libraries tự viết implement `javax.servlet.Filter`.

Nếu nâng một filter sang Jakarta nhưng giữ framework cũ sử dụng `javax.servlet.*`, build hoặc runtime có thể thất bại. Khi đó “đúng phạm vi” **không phải ép toàn hệ thống sửa mọi import trong một commit**, mà là xác định nhóm phụ thuộc chặt phải cùng chuyển ở runtime boundary.

Chiến lược:

```text
Inventory API/container dependencies
              |
              v
Choose compatible target runtime group
              |
              v
Migrate small component in isolated branch
              |
              v
Test with target API + target container
              |
              v
Migrate surrounding tightly coupled components
              |
              v
Deploy group at coherent boundary
```

Những module nghiệp vụ không sử dụng Servlet types có thể để nguyên. Trong một monolith chia modules, không nhất thiết domain layer phải import Jakarta chỉ vì web layer được nâng.
## 23. Nếu ứng dụng dùng web.xml thay vì annotation

Một số WAR legacy chỉ đăng ký filter bằng `WEB-INF/web.xml`. Không nên xóa một cơ chế đăng ký đang có để dùng `@WebFilter` chỉ vì muốn code ít dòng, nhất là khi thứ tự filter liên quan security.

Mẫu khai báo target Jakarta Servlet 6.0:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app
    xmlns="https://jakarta.ee/xml/ns/jakartaee"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/jakartaee
        https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
    version="6.0">

    <filter>
        <filter-name>requestIdFilter</filter-name>
        <filter-class>
            com.example.web.RequestIdFilter
        </filter-class>
    </filter>

    <filter-mapping>
        <filter-name>requestIdFilter</filter-name>
        <url-pattern>/api/*</url-pattern>
        <dispatcher>REQUEST</dispatcher>
    </filter-mapping>
</web-app>
```

Nếu dùng `web.xml`:
- Xem XML namespace/schema version tương thích Servlet container.
- Xác định đúng `filter-class` và mapping.
- Giữ `dispatcher`/async-supported/initialization parameters theo nhu cầu gốc.
- **Gỡ `@WebFilter` khỏi class** trong biến thể này để tránh tạo hai cách registration với cùng mục tiêu.
- Kiểm tra thứ tự các `filter-mapping` trong descriptor theo cấu hình ứng dụng thực tế.
- Deploy WAR lên container đích và thực thi integration tests.

Với project WAR mẫu ở các mục trước, hãy **chọn một cách**: annotation *hoặc* descriptor. Cách dùng annotation đã đủ, không cần bổ sung file trên để bài mẫu chạy.

## 24. Gradle là lựa chọn thay thế Maven, không phải thêm song song

Nếu project thật sử dụng Gradle, có thể chọn `build.gradle.kts` thay vì `pom.xml`. Mẫu riêng cho cùng WAR và Jakarta Servlet:

```kotlin
plugins {
    java
    war
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    compileOnly("jakarta.servlet:jakarta.servlet-api:6.0.0")

    testImplementation("jakarta.servlet:jakarta.servlet-api:6.0.0")
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testImplementation("org.mockito:mockito-core:5.15.2")

    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
```

Trong ví dụ này:
- `compileOnly` giúp biên dịch nhưng **không** đưa Servlet API vào runtime WAR như một thư viện ứng dụng.
- `testImplementation` cho Jakarta Servlet API bảo đảm mock-based unit tests có interface lúc chạy test.
- Container mục tiêu cung cấp Servlet API lúc deploy WAR.
- `war` plugin tạo artifact phù hợp external servlet container.
- Toolchain Java 17 phải tồn tại/có khả năng được Gradle provision theo cấu hình môi trường.

Gradle version phải hỗ trợ JDK/toolchain mục tiêu. Đây là một **lựa chọn thay thế**, không cần giữ cả Maven và Gradle trong cùng workshop. Chạy `./gradlew clean test war` khi dự án Gradle đã được cấu hình; không mặc định lệnh này đúng cho mọi project multi-module.

## 25. Kiểm thử Servlet API đúng scope

Câu hỏi: nếu WAR không chứa `jakarta.servlet-api` thì vì sao unit tests vẫn chạy được?

Đáp án:
- Maven dependency `provided` có mặt lúc compile và test nhưng không đưa vào runtime classpath của WAR theo vai trò container.
- Gradle tách `compileOnly` và `testImplementation` như mẫu để cung cấp API cho tests.
- Tomcat 10.1 cung cấp Servlet implementation/API trong deployment runtime.

Một sơ đồ:

```text
Developer compile/tests
      |
      +--> RequestIdFilter.class
      +--> jakarta.servlet-api (compile/test only)
      +--> JUnit + Mockito (test only)
      |
      v
WAR artifact
      |
      +--> WEB-INF/classes/RequestIdFilter.class
      +--> WEB-INF/classes/PingServlet.class
      |
      v
Tomcat 10.1 runtime
      |
      +--> Jakarta Servlet API/implementation
      +--> WAR classes + application dependencies
```

Sai lầm “thử thêm Servlet API JAR vào WAR xem hết lỗi không” có thể che lỗi lựa chọn container sai hoặc tạo phân mảnh classloader. Trước khi thay scope, phải xác định loại deployment: standalone container, embedded server hay application server; từng loại có contract dependency khác nhau.

## 26. Rà soát source bằng giới hạn rõ

Khi migration thực tế, thay vì chạy toàn repository:

```text
Find:    javax.
Replace: jakarta.
```

hãy đặt **allowlist** của namespace thuộc thành phần:

```text
javax.servlet.Filter
javax.servlet.FilterChain
javax.servlet.ServletRequest
javax.servlet.ServletResponse
javax.servlet.ServletException
javax.servlet.DispatcherType
javax.servlet.annotation.WebFilter
javax.servlet.http.HttpServletResponse
```

Sau đó chỉ sửa đúng source file và metadata liên quan. Giữ những class Java SE khác không đổi.

Có thể dùng compile, IDE find-usages và bytecode inspection để phát hiện các reference `javax.servlet` còn tồn tại trong artifact đã tạo. Tuy nhiên:
- Search source không thấy binary-only dependency.
- Một JAR bên thứ ba có thể chứa `javax.servlet` reference dù application code đã sạch.
- Generated code có thể tái tạo legacy imports sau build.
- Service metadata, web descriptors hoặc JSP/taglibs có thể còn dùng kiểu cũ.

Vì vậy, kiểm kê các vùng thực tế sử dụng Servlet API, nhưng **không chuyển các module không liên quan chỉ vì chúng có `javax.*` trong tên package**.

## 27. Kiểm tra dependency graph khi phát sinh lỗi

Với Maven:

```bash
mvn dependency:tree
mvn help:effective-pom
```

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency servlet \
  --configuration compileClasspath
```

Xem:
1. API family đang được chọn: `javax.servlet-api` hay `jakarta.servlet-api`?
2. API version có phù hợp container không?
3. Có library/plugin bên thứ ba yêu cầu namespace cũ không?
4. Có duplicate Servlet API JAR ở WAR hoặc classpath của server không?
5. Có dependency được `provided` nhưng runtime thực sự không cung cấp không?
6. Có artifact cũ bị shading/relocation hoặc classloader cô lập không?

Ví dụ lỗi:

```text
java.lang.NoClassDefFoundError:
    jakarta/servlet/Filter
```

có thể là container không cung cấp API mới. Ví dụ khác:

```text
java.lang.NoClassDefFoundError:
    javax/servlet/Filter
```

trong Jakarta runtime có thể là một third-party filter library vẫn được biên dịch cho Java EE. Lỗi compile còn có thể là conflicting interfaces/method signatures nếu import bị trộn.

Đọc **toàn bộ Caused by chain** thay vì chỉ thêm JAR đầu tiên mà thông báo gợi ý.

## 28. Dùng jdeps đúng vai trò

Trên JDK 17, `jdeps` có thể giúp tìm class-level references trong bytecode:

```bash
jdeps --ignore-missing-deps \
  --verbose:class \
  target/classes
```

Với một WAR, có thể cần phân tích `WEB-INF/classes` và JARs riêng tùy cách công cụ nhận path. `jdeps` phân tích **dependency tĩnh**, không thể đảm bảo tìm mọi nơi nạp class qua reflection, ServiceLoader hoặc XML metadata.

Khi xem output, mục tiêu là xác định:
- Class nào còn phụ thuộc `javax.servlet.*`.
- Class nào đã phụ thuộc `jakarta.servlet.*`.
- Có các thư viện khác yêu cầu container API khác không.
- Một dependency nào đang bị thiếu hoặc module graph không đầy đủ.

Lưu ý `--ignore-missing-deps` có thể che báo cáo lỗi thiếu dependency để cho phép xem các reference còn lại; không được coi **không lỗi từ lệnh này** là bằng chứng mọi class dependency đều có mặt. Dùng thêm runtime integration test.

## 29. Trường hợp thư viện bên thứ ba chưa có bản Jakarta

Giả sử một legacy monitoring filter được phân phối dưới dạng binary JAR:

```java
public final class LegacyMonitorFilter
        implements javax.servlet.Filter {
    // ...
}
```

Ứng dụng mới dùng `jakarta.servlet.Filter`. Có ba hướng chính:

1. **Nâng thư viện** lên bản Jakarta chính thức từ vendor.
2. **Thay thế thư viện** bằng component Jakarta-compatible có contract tương đương.
3. **Cô lập** tính năng legacy ở một ứng dụng/runtime cũ và giao tiếp với ứng dụng mới qua boundary trung lập như HTTP/queue, nếu nghiệp vụ cho phép.

Một số công cụ bytecode/archive migration có thể đổi reference namespace trong binary, nhưng cần đánh giá mức hỗ trợ, giấy phép, runtime integration, resources/metadata và tests đầy đủ. **Không mặc định “transform” mọi library cũ là an toàn hoặc luôn thành công.**

Nếu ứng dụng bắt buộc giữ cả hai thế hệ trong giai đoạn chuyển:
- Có thể chạy **hai ứng dụng riêng**, một bên Tomcat 9 và một bên Tomcat 10.1.
- Dùng một API/protocol trung lập giữa chúng.
- Giữ DTO/shared domain không đưa Servlet types `javax` hoặc `jakarta` ra boundary.
- Dùng contract tests cho HTTP/events.
- Kết thúc giai đoạn hỗ trợ cũ khi đã có bằng chứng.

Không cố triển khai cùng một binary Servlet Filter làm instance tương thích với cả hai interface bằng casting.

## 30. Điều chỉnh phạm vi với interface ở tầng domain

Để tránh “rò” Servlet type xuống domain layer, tách contract:

```text
                 Web Adapter (Jakarta Servlet)
                           |
                           v
               Application Service Interface
                           |
                           v
                        Domain
```

Ví dụ domain/app service dùng Java SE types, không cần thay khi web layer nâng:

```java
package com.example.domain;

public interface RequestAudit {
    void record(String requestId, String path);
}
```

Một Jakarta adapter có thể lấy dữ liệu từ `HttpServletRequest` rồi gọi `record(...)`. Bản Java EE cũ cũng có thể gọi cùng interface này từ adapter `javax.servlet.*` trong một deployment **riêng**.

Ưu điểm:
- Domain contract giữ nguyên.
- Test domain không cần container API.
- Chuyển đổi Servlet adapter nhỏ, cô lập.
- Giảm khả năng một thay đổi namespace kéo theo nhiều module.
- Rollback có thể giữ business logic trong khi đổi adapter/runtime.

**Đây là chiến lược thiết kế**, không có nghĩa phải viết lại domain layer của workshop `RequestIdFilter`. Với một filter đơn giản, việc giữ logic tạo UUID tại filter cũng hợp lý.

## 31. Security implications của một filter khi migration

Filter trong bài chỉ sinh request ID, không xác thực người dùng. Nhưng trong hệ thống thật, filter chain có thể chứa authentication, authorization, CSRF, CORS, logging, request wrapping và exception handling.

Khi đổi Servlet namespace, kiểm tra:
- Thứ tự filter so với security filters.
- Những URL nào được bypass/match.
- Dispatcher types REQUEST/FORWARD/ERROR/ASYNC.
- Async context propagation và thread-local cleanup.
- Có filter register hai lần không.
- Có thay đổi cách response được commit không.
- Có exception bị nuốt trước khi Spring Security hoặc container xử lý không.
- Có thông tin nhạy cảm được log/header hóa không.

**X-Request-ID không phải bằng chứng xác thực.** Một request ID là dữ liệu tương quan log, không nên dùng để phân quyền hoặc tin rằng client nào cung cấp đúng ID thì có quyền. Nếu chấp nhận inbound X-Request-ID từ proxy hoặc client, cần chính sách độ dài, định dạng, nguồn tin cậy và chống log injection; bài này **tự sinh UUID** để giữ ví dụ an toàn và dễ kiểm thử.

## 32. Thay đổi metadata deployment có thể mở rộng phạm vi ngoài ý muốn

Những thay đổi cần rà:
- Descriptor namespace/schema version.
- `@WebFilter` vs `web.xml`.
- URL pattern `/api/*` vs `/*`.
- Filter name và mapping order.
- `asyncSupported` và các dispatcher types.
- Static resource handling.
- Error/forward mapping.
- Context path.
- Multiple servlet registrations.
- Reverse proxy/ingress path rewrite.

Một lỗi ví dụ:

```java
@WebFilter("/*")
```

nếu trước đây filter chỉ áp dụng `/api/*`, có thể gây thay đổi behavior cho login, static content, file upload hoặc error pages. Đừng mở rộng mapping để “cho chắc” khi migration.

Một lỗi khác là không khai báo dispatcher types theo contract cũ. Trong bài chính, ta dùng:

```java
dispatcherTypes = { DispatcherType.REQUEST }
```

Nếu hệ thống thật trước đây xử lý cả ASYNC hoặc ERROR, phải chuyển đúng behavior đã cam kết và có test riêng.

## 33. Canary và rollback ở cấp runtime group

Một vấn đề thực tế: không thể “rollback riêng một class Filter” nếu WAR mới đã dùng Jakarta Servlet và runtime đã chuyển từ Tomcat 9 lên 10.1.

Có thể triển khai theo nhóm:

```text
        Load Balancer / Gateway
                |
       +--------+--------+
       |                 |
       v                 v
Legacy WAR +         Jakarta WAR +
Tomcat 9             Tomcat 10.1
       |                 |
       +--------+--------+
                |
            Shared DB/API
```

Trong giai đoạn canary, hai runtime chạy riêng. Điều kiện:
- API trả hành vi giống contract ở những endpoint tương đương.
- Dữ liệu/DB/messaging tương thích hai phía.
- Session/cookies/authentication flow được thiết kế cho rollout.
- Load balancer route và header forwarding đúng.
- Metrics phân biệt legacy/new version.
- Có cách đưa traffic quay về legacy **nếu dữ liệu và security policy cho phép**.

Nếu migration còn đổi database schema, rollback không chỉ là đổi route về Tomcat 9. Với component không có state như filter request ID, phạm vi rủi ro dữ liệu nhỏ hơn, nhưng runtime/framework group vẫn cần đồng bộ khi rollback.

Không giữ Java EE runtime cũ lâu dài nếu đã hết support/security patches; canary window cần có ngày kết thúc và lộ trình gỡ bỏ.

## 34. Các tiêu chí nghiệm thu có thể đo được

| Gate | Điều kiện | Bằng chứng |
|---|---|---|
| Scope | Chỉ Servlet-facing imports cần thiết được đổi, Java SE `javax.*` vẫn nguyên. | Diff, dependency inventory. |
| Build | Compile với Java 17, Jakarta Servlet 6 API. | Maven/Gradle build output. |
| Unit | Header/attribute/chain/exception tests xanh. | JUnit report. |
| Artifact | WAR có classes đích, không bundling Servlet API sai. | `jar tf`, dependency report. |
| Runtime | Deploy được trên Tomcat 10.1. | Container logs, deploy status. |
| URL mapping | `/api/*` khớp, ngoài phạm vi không bị filter xử lý. | HTTP integration tests. |
| No regressions | Same response contract và error propagation. | Before/after contract matrix. |
| Namespace | Không có reference `javax.servlet` trong migrated component. | Source/bytecode inspection. |
| Container family | Không còn WAR Jakarta deploy nhầm vào container javax. | Deployment config và inventory. |
| Security | Không thay filter order/security boundaries ngoài ý định. | Security regression tests nếu có. |
| Operations | Rollback/canary route được định nghĩa. | Release runbook. |

Kết quả ở đây là **mẫu acceptance criteria cho người học thực hiện**, không phải một báo cáo đã chạy trên một dự án thật.

## 35. Bài tập nâng cao 1: thêm case dispatcher types

Yêu cầu:
- Giữ `RequestIdFilter` chỉ chạy cho `DispatcherType.REQUEST` như mẫu.
- Tạo một endpoint báo lỗi và cho container dispatch tới error page.
- Kiểm tra filter không tự chạy lại do `ERROR` dispatch nếu mapping không chọn kiểu đó.
- Nếu dự án muốn filter trên `ERROR`, thay mapping có chủ đích và bổ sung test cho trace ID across dispatches.

Câu hỏi:
1. Có nên tự động set lại một request ID khác trong error dispatch không?
2. Một header đã được commit có thể thay đổi sau đó không?
3. Nếu có async, việc dùng request attribute có được truyền đúng như framework mong đợi không?

Gợi ý: đối với tracing, cần cùng correlation ID xuyên suốt xử lý; nhưng policy phụ thuộc request lifecycle và filter registration. Test theo container thật thay vì phỏng đoán từ annotation.

## 36. Bài tập nâng cao 2: tìm package javax không được đổi

Cho danh sách:

```text
javax.servlet.http.HttpServletRequest
javax.sql.DataSource
javax.crypto.Mac
javax.validation.constraints.NotNull
javax.net.ssl.HttpsURLConnection
javax.persistence.Entity
javax.xml.parsers.SAXParserFactory
javax.naming.Context
javax.annotation.PostConstruct
javax.tools.ToolProvider
```

Hãy chia thành ba nhóm:

- **Nhóm A:** chuyển trong Servlet API migration.
- **Nhóm B:** chỉ xem xét chuyển khi cùng lúc nâng những nhóm Jakarta EE khác như Persistence/Validation/Annotations.
- **Nhóm C:** giữ nguyên vì thuộc Java SE.

Đáp án gợi ý:

| Tên | Nhóm |
|---|---|
| `javax.servlet.http.HttpServletRequest` | A → `jakarta.servlet.http.HttpServletRequest`. |
| `javax.sql.DataSource` | C. |
| `javax.crypto.Mac` | C. |
| `javax.validation.constraints.NotNull` | B → Jakarta Validation tương ứng khi nâng validation stack. |
| `javax.net.ssl.HttpsURLConnection` | C. |
| `javax.persistence.Entity` | B → Jakarta Persistence khi nâng JPA stack. |
| `javax.xml.parsers.SAXParserFactory` | C. |
| `javax.naming.Context` | C. |
| `javax.annotation.PostConstruct` | B → Jakarta Annotations khi nâng API/framework liên quan. |
| `javax.tools.ToolProvider` | C. |

Bài tập này ngăn một lỗi rất phổ biến: coi tiền tố `javax` là bằng chứng class cần đổi, thay vì xác định **API specification mà class thuộc về**.
## 37. Bài tập nâng cao 3: không biến tracing thành lỗ hổng

Giả sử yêu cầu mới là giữ `X-Request-ID` từ API gateway để nối log giữa nhiều services. Cách làm sơ sài:

```java
String id = httpRequest.getHeader("X-Request-ID");
response.setHeader("X-Request-ID", id);
```

có các rủi ro:
- Header có thể vắng mặt hoặc rỗng.
- Client bên ngoài có thể tự giả mạo ID của một request khác.
- Giá trị quá dài hoặc chứa ký tự không mong muốn gây log/metric issues.
- Phụ thuộc request ID như một access token tạo lỗ hổng authorization.
- Khi proxy forward nhiều bản cùng tên, giá trị nào được chọn không rõ ràng.

Yêu cầu cho bài nâng cao:
1. Chỉ tin inbound ID nếu request đến từ **gateway tin cậy** theo boundary được thiết kế.
2. Kiểm tra định dạng và giới hạn độ dài.
3. Với ID không hợp lệ, tạo UUID mới.
4. Không đưa credential, session ID hay raw PII vào correlation header.
5. Giữ ID nhất quán giữa request attribute, response header và log context.
6. Nếu dùng MDC/thread-local, cleanup trong `finally` và kiểm thử async/error dispatch.

Đây là một **thay đổi nghiệp vụ/observability riêng**, không nên làm lẫn trong commit migration `javax` → `jakarta` nếu mục tiêu hiện tại chỉ giữ nguyên contract. Cách giảm rủi ro là hoàn tất namespace migration trước, sau đó mở một change request riêng cho logic header mới.

## 38. Một trình tự PR thực tế ít rủi ro

Trong dự án lớn, có thể chia công việc thành các pull requests theo ranh giới:

### PR A — Chuẩn bị khả năng kiểm thử

- Chụp baseline behavior của filter hiện tại.
- Ghi URL mappings, ordering và dispatcher types.
- Tạo contract tests hoặc fixtures có thể chạy trên môi trường cũ.
- Inventory dependency `javax.servlet` và các Java SE imports phải giữ.

PR này không cần đổi runtime ngay.

### PR B — Đồng bộ runtime family

- Chốt Java runtime, Servlet API, Tomcat/Spring version mục tiêu.
- Nâng framework/dependency liên quan theo nhóm tương thích.
- Chuẩn bị pipeline hoặc deployment mới hỗ trợ Jakarta.
- Đảm bảo những thành phần web khác trong cùng WAR có kế hoạch nâng đồng bộ.

Đây có thể là PR lớn hơn filter, vì Servlet-facing interfaces thuộc một **runtime boundary thống nhất**.

### PR C — Chuyển component và test

- Đổi `RequestIdFilter` sang Jakarta imports.
- Giữ nguyên method behavior và URL mapping.
- Chuyển test mocks sang Jakarta interfaces.
- Dùng đúng API dependency scopes.
- Build/package WAR và thử trên Tomcat 10.1.

### PR D — Rollout và cleanup

- Canary traffic qua runtime mới.
- So sánh header, lỗi, access logs và latency.
- Xác minh không còn unexpected `javax.servlet` links trong migrated WAR.
- Loại legacy deployment theo cửa sổ rollback.
- Gỡ temporary bridges/dependency overrides có chủ đích.
- Cập nhật runbook, compatibility matrix, alerting và tài liệu.

Cách chia có thể thay đổi tùy monolith, nhưng nên tránh **trộn sửa namespace với refactor nghiệp vụ lớn** trong cùng một commit khó kiểm tra.

## 39. Những dấu hiệu cho thấy “đúng phạm vi” đã thất bại

Một code review nên yêu cầu giải thích khi thấy:
- Hàng trăm import `javax.sql`, `javax.crypto` bị thay không có lý do.
- Business domain bắt đầu nhận `jakarta.servlet.http.HttpServletRequest` làm parameter.
- Một `Filter` chuyển namespace nhưng Tomcat vẫn 9.x.
- WAR mới bundling cả `javax.servlet-api` lẫn `jakarta.servlet-api`.
- Filter mapping đổi từ `/api/*` sang `/*` mà không có contract change.
- Người viết đồng thời thay logic authentication/tracing và không có tests.
- Unit tests dùng mock Jakarta nhưng production vẫn chạy container Java EE.
- Bytecode transformer được áp lên tất cả JAR, không có phạm vi và danh sách exclude.
- Dependency transitive tự kéo web stack không tương thích.
- Generated sources vẫn import legacy Servlet types dù source chính đã được sửa.

Đừng sửa biểu hiện bề ngoài bằng cách nhét thêm thư viện hoặc suppress exception. Cần tìm phần nào của **class identity/runtime contract** chưa đồng bộ.

## 40. Quy trình thao tác tóm lược theo thứ tự

1. **Chọn thành phần:** `RequestIdFilter` và những Servlet types trực tiếp của nó.
2. **Đánh dấu không đổi:** `java.util.UUID`, `java.io.IOException`, Java SE `javax.*` khác.
3. **Chốt đích:** JDK 17, Jakarta Servlet 6.0, Tomcat 10.1 cho WAR thử nghiệm.
4. **Ghi hợp đồng:** đường dẫn `/api/*`, header, request attribute, chain/error behavior.
5. **Tạo baseline:** kiểm tra hiện trạng javax trên container đời cũ nếu có.
6. **Đổi đủ imports và chữ ký:** tất cả type Servlet thuộc Jakarta.
7. **Đổi dependency:** dùng Jakarta Servlet API `provided` cho WAR.
8. **Chuyển test:** Mock Jakarta ServletRequest/Response/FilterChain.
9. **Build và inspect:** xác nhận class implement `jakarta.servlet.Filter` và WAR không bundle API sai.
10. **Deploy vào đúng container:** Tomcat 10.1 chứ không phải Tomcat 9.
11. **Integration test:** `GET /api/ping`, header/attribute, mapping ngoài phạm vi, exception flow.
12. **Kiểm tra thư viện liên quan:** không có unresolved `javax.servlet` references trong cùng runtime group.
13. **Canary và rollback:** theo đúng nhóm runtime, không giả định có thể thay một class trên server cũ.
14. **Dọn cấu hình tạm:** sau khi đạt gate và hết support/rollback window.
15. **Ghi bằng chứng:** code diff, versions, test reports, WAR checksum, container runtime và người duyệt.

**Lưu ý về trình tự:** nếu runtime chưa thể chuyển, chỉ có thể chuẩn bị mã/adapter ở nhánh khác; không đưa ngay binary Jakarta lên một WAR/container vẫn yêu cầu javax.

## 41. Câu hỏi tự kiểm tra

**Câu 1:** Vì sao `javax.sql.DataSource` không đổi thành `jakarta.sql.DataSource` trong bài thực hành?

Vì `javax.sql` thuộc Java SE, không phải Servlet/Jakarta EE API được chuyển namespace trong phạm vi này.

**Câu 2:** Có thể triển khai `RequestIdFilter implements jakarta.servlet.Filter` lên Tomcat 9 nếu thêm `jakarta.servlet-api.jar` vào WAR không?

Không thể coi đó là giải pháp đúng. Tomcat 9 sử dụng contract `javax.servlet.Filter`; class Jakarta không trở thành Javax Filter do thêm JAR. Cần dùng container/framework Jakarta-compatible hoặc giữ bản Javax ở deployment cũ.

**Câu 3:** Vì sao scope `provided` thích hợp cho `jakarta.servlet-api` trong WAR external Tomcat?

Vì cần API để compile/test, còn Servlet API/implementation được Tomcat cung cấp khi deploy. WAR không nên tự gói một bản API khác trái contract của container.

**Câu 4:** Unit tests xanh đã chứng minh `@WebFilter` được container phát hiện chưa?

Chưa. Unit tests chỉ gọi Java method trực tiếp; cần integration test deploy WAR trên container đích và đi qua HTTP request thật.

**Câu 5:** Nếu muốn dùng `web.xml`, có nên giữ `@WebFilter` cùng logic đăng ký không?

Không nên tự ý để hai đường registration cho cùng filter. Chọn một cơ chế rõ ràng, giữ mapping/order/dispatch behavior và test container thực tế.

**Câu 6:** Khi thay import Jakarta, có cần thay `java.util.UUID` thành một package mới không?

Không. `java.util.UUID` thuộc Java SE, hoàn toàn không nằm trong chuyển đổi Java EE namespace.

**Câu 7:** Vì sao không nên đồng thời thay đổi thuật toán sinh request ID trong cùng PR?

Vì sẽ khó phân biệt lỗi do namespace/runtime với lỗi do thay đổi logic, và khiến baseline contract không còn ổn định.

**Câu 8:** Một dependency dùng `javax.servlet.Filter` nhưng được đóng gói cạnh filter Jakarta có tự tương thích không?

Không. Hai interface có type identity khác nhau; thư viện cần bản Jakarta-compatible hoặc một migration/adapter được thiết kế theo boundary tương thích.

## 42. Checklist trước khi coi bài thực hành hoàn tất

- [ ] Đã xác định component cần chuyển và phạm vi source được phép sửa.
- [ ] Đã liệt kê những Java SE `javax.*` **không** được đổi.
- [ ] Đã chọn đúng Servlet API version và container tương thích.
- [ ] Đã xác minh Java version/toolchain dùng build.
- [ ] `RequestIdFilter` implement `jakarta.servlet.Filter`.
- [ ] `FilterChain`, `ServletException`, `ServletRequest`, `ServletResponse` và annotation cùng thuộc Jakarta namespace.
- [ ] `java.io.IOException` và `java.util.UUID` được giữ nguyên.
- [ ] `/api/*` và dispatcher type không bị đổi ngoài ý muốn.
- [ ] Request attribute và header chứa cùng request ID.
- [ ] Filter gọi `chain.doFilter` đúng một lần.
- [ ] `ServletException` và `IOException` được truyền đúng cho downstream error handling.
- [ ] Unit tests có cả happy path và error path.
- [ ] WAR build output có implementation class mong đợi.
- [ ] Servlet API dependency không bị đóng gói sai scope.
- [ ] Không có reference `javax.servlet.*` ngoài kế hoạch trong runtime group đã nâng.
- [ ] WAR được deploy trên Tomcat 10.1 hoặc container Jakarta Servlet 6 tương thích.
- [ ] HTTP integration test xác nhận route/filter mapping thực tế.
- [ ] Không có đăng ký filter trùng qua annotation, XML và framework.
- [ ] Security filter ordering/authorization không bị thay đổi ngoài phạm vi.
- [ ] Đã xác nhận các thư viện phụ thuộc chặt cũng tương thích Jakarta.
- [ ] Có kế hoạch canary/rollback theo runtime group.
- [ ] Diff/test evidence, artifact version và container runtime được ghi lại.

## 43. Tài liệu tham khảo

- [Jakarta Servlet 6.0 Specification](https://jakarta.ee/specifications/servlet/6.0/): đặc tả Servlet API, lifecycle, filters và deployment.
- [Apache Tomcat — Which Version?](https://tomcat.apache.org/whichversion.html): bảng đối chiếu Tomcat, Jakarta Servlet và Java baseline.
- [Apache Tomcat — Migration Guide Tomcat 10](https://tomcat.apache.org/migration-10.html): thay đổi Java EE `javax.*` → Jakarta EE `jakarta.*` khi nâng Tomcat 9 → 10.
- [Apache Tomcat — Migration Guide Tomcat 10.1](https://tomcat.apache.org/migration-10.1.html): các thay đổi của Tomcat 10.1/Jakarta Servlet 6.0.
- [Apache Tomcat — Jakarta EE Migration Tool](https://tomcat.apache.org/download-migration.cgi): công cụ chuyển đổi một số ứng dụng/binary archive legacy, có phạm vi và giới hạn cần đánh giá.
- [Jakarta EE Specifications](https://jakarta.ee/specifications/): phân biệt Servlet, Persistence, Validation, Annotations và các API Jakarta khác.
- [Maven Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): compile/runtime/provided/test scopes.
- [Maven WAR Plugin](https://maven.apache.org/plugins/maven-war-plugin/): đóng gói ứng dụng web.
- [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/): chạy unit tests.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): xây dựng các tests.
- [Mockito Documentation](https://site.mockito.org/): mock ServletRequest/ServletResponse/FilterChain.
- [Gradle WAR Plugin](https://docs.gradle.org/current/userguide/war_plugin.html): đóng gói WAR trong Gradle.
- [Spring Boot Reference](https://docs.spring.io/spring-boot/reference/): tích hợp Servlet container và filter registration cho dự án Spring Boot.
- [Spring Security Reference](https://docs.spring.io/spring-security/reference/): cấu hình filter chain và security boundary nếu filter nằm trong ứng dụng Spring Security.

## Kết luận

Chuyển một thành phần từ **`javax.servlet.*` sang `jakarta.servlet.*` đúng phạm vi** không phải thao tác đổi chuỗi trên toàn repository. Với `RequestIdFilter`, cần xác định trước Servlet API owner, giữ nguyên Java SE APIs và hợp đồng nghiệp vụ, đổi đầy đủ Java types/annotations có liên quan, sau đó đồng bộ Maven/Gradle dependency cùng Servlet container để tránh trộn hai thế hệ class identity.

Bài thực hành hoàn tất về mặt kỹ thuật khi unit tests giữ nguyên header, request attribute và chain behavior; WAR chứa class Jakarta đúng scope; Tomcat 10.1 thực sự nhận filter và xử lý request; và nhóm có bằng chứng không ảnh hưởng các Java SE `javax.*` hoặc những module ngoài phạm vi. Bài học rộng hơn là **giới hạn code change nhưng không bỏ sót runtime boundary**: một sửa đổi nhỏ vẫn cần một hệ dependency/container nhất quán. Đây là cách nâng Jakarta có thể kiểm thử, có thể giải thích và có thể rollback trong các chương trình Java compatibility migration.







