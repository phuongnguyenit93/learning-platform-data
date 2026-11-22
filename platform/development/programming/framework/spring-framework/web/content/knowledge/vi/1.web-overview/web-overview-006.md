# Phiên bản Spring, Jakarta Servlet và khả năng tương thích của API

## 1. Vì sao phải kiểm tra phiên bản trước khi viết ứng dụng web?

Một ứng dụng **Spring Web MVC** không chạy độc lập khỏi các lớp nền tảng: mã Java được biên dịch bằng JDK, sử dụng Spring Framework và các API Servlet, rồi được phục vụ bởi một Servlet container như Tomcat hoặc Jetty. Nếu dùng Spring Boot, Boot chọn và quản lý phần lớn phiên bản phụ thuộc và thường khởi động container nhúng.

Có bốn câu hỏi riêng biệt:

1. **JDK nào?** Ví dụ Java 8, 17, 21 hoặc 25; JVM phải chạy được bytecode và thỏa yêu cầu tối thiểu của Spring/container.
2. **Spring Framework nào?** Ví dụ 5.3, 6.2 hoặc 7.0; mỗi thế hệ có mức Java/Jakarta EE tối thiểu và thay đổi API riêng.
3. **API Servlet nào?** Ví dụ Servlet 4.0 (`javax.servlet.*`), Jakarta Servlet 5.0/6.0/6.1 (`jakarta.servlet.*`); đây là hợp đồng giữa mã web và container.
4. **Container nào?** Ví dụ Tomcat 9/10.1/11; container *triển khai* một phiên bản Servlet, chứ việc thêm một JAR Servlet API không tự nâng cấp container.

**Phạm vi bài:** web stack dựa trên Servlet của Spring MVC (`spring-webmvc`). Spring WebFlux có thể chạy trên Reactor Netty và không nhất thiết sử dụng Servlet API; vì vậy không áp bảng tương thích container Servlet một cách máy móc cho mọi ứng dụng WebFlux.

## 2. Bản đồ tương thích cần nhớ

| Thế hệ ứng dụng điển hình | Java tối thiểu | API web/namespace | Servlet container điển hình | Điều cần nhớ |
| --- | --- | --- | --- | --- |
| Spring Framework **5.3** / Spring Boot **2.7** | Java 8 | Java EE 8, **Servlet 4.0**, `javax.servlet.*` | **Tomcat 9** | Dòng cũ trước chuyển đổi namespace. |
| Spring Framework **6.0–6.2** / Spring Boot **3.x** | Java 17 | Jakarta EE 9+, **Servlet 5.0+**, `jakarta.servlet.*` | Boot 3.5 nhúng **Tomcat 10.1 / Servlet 6.0** | Servlet 5.0 là mức API tối thiểu của thế hệ Spring 6; phiên bản nhúng thực tế có thể cao hơn. |
| Spring Framework **7.0** / Spring Boot **4.x** | Java 17 | Jakarta EE 11, **Servlet 6.1+**, `jakarta.servlet.*` | **Tomcat 11 / Servlet 6.1**, hoặc Jetty 12.1 | Nâng baseline Servlet; không thể mặc định triển khai lên Tomcat 10.1. |

**Cách đọc bảng:** đây là quan hệ giữa *các dòng phiên bản*, không phải khẳng định mọi bản vá Spring Boot chọn cùng một bản Spring Framework. Chẳng hạn, Boot 3.5 sử dụng dòng Framework 6.2; Boot 4.0/4.1 sử dụng dòng Framework 7.0. Xem dependency management/BOM của đúng phiên bản Boot đang dùng để biết phiên bản thư viện thực tế.

Bảng riêng cho **Tomcat và Servlet**:

| Tomcat | Servlet specification | Namespace |
| --- | --- | --- |
| 9.0.x | 4.0 | `javax.servlet.*` |
| 10.0.x (đã hết hỗ trợ) | 5.0 | `jakarta.servlet.*` |
| 10.1.x | 6.0 | `jakarta.servlet.*` |
| 11.0.x | 6.1 | `jakarta.servlet.*` |

**Hai lưu ý dễ nhầm:**

- Tên tổ chức *Jakarta EE 8* đã xuất hiện trước khi đổi package; các API Jakarta EE 8/Servlet 4.0 vẫn dùng namespace `javax.*`. **Jakarta EE 9/Servlet 5.0** mới là mốc đổi sang `jakarta.*`.
- Các mức Java tối thiểu trong bảng là mức của *Spring Framework/thế hệ ứng dụng*. Một container riêng có thể yêu cầu Java thấp hơn, nhưng toàn bộ ứng dụng vẫn phải đáp ứng **mức cao nhất** trong các thành phần. Ví dụ Tomcat 10.1 có thể chạy với Java 11, nhưng Spring Framework 6 vẫn cần Java 17+.

## 3. Servlet API nằm ở đâu trong Spring MVC?

Luồng xử lý rút gọn:

```text
HTTP client
    |
    v
Servlet container (Tomcat/Jetty)
    |
    v
jakarta.servlet.Filter chain
    |
    v
Spring DispatcherServlet
    |
    v
HandlerMapping -> @Controller/@RestController -> HandlerAdapter
    |
    v
HttpMessageConverter / ViewResolver
    |
    v
HTTP response
```

`DispatcherServlet` là một Servlet do Spring MVC cung cấp. Spring sử dụng những đối tượng từ Servlet API như `HttpServletRequest`, `HttpServletResponse`, `ServletContext`, `Filter`, `ServletRegistration`. Container tạo và quản lý vòng đời request/response, filter, servlet; Spring thực hiện routing, binding, gọi handler, xử lý lỗi và tạo phản hồi.

Chẳng hạn, chữ ký sau phụ thuộc trực tiếp vào namespace của Servlet API:

```java
// Spring Framework 5.3 / Spring Boot 2.x
import javax.servlet.http.HttpServletRequest;

// Spring Framework 6+ / Spring Boot 3+
import jakarta.servlet.http.HttpServletRequest;
```

Đây là **hai kiểu Java khác nhau** có tên đầy đủ khác nhau; chúng không tự hoán đổi được chỉ vì cùng có tên `HttpServletRequest`. Tương tự: `javax.servlet.Filter` khác `jakarta.servlet.Filter`.

## 4. Điểm gãy lớn: Java EE → Jakarta EE

Khi các đặc tả enterprise chuyển sang Jakarta EE, các API chịu ảnh hưởng thay đổi namespace. Với ứng dụng web, ví dụ thường gặp:

| Trước (Java EE 8) | Sau (Jakarta EE 9+) | Vai trò |
| --- | --- | --- |
| `javax.servlet.http.HttpServletRequest` | `jakarta.servlet.http.HttpServletRequest` | Request HTTP |
| `javax.servlet.http.HttpServletResponse` | `jakarta.servlet.http.HttpServletResponse` | Response HTTP |
| `javax.servlet.Filter` | `jakarta.servlet.Filter` | Filter |
| `javax.servlet.annotation.WebFilter` | `jakarta.servlet.annotation.WebFilter` | Đăng ký filter |
| `javax.validation.Valid` | `jakarta.validation.Valid` | Bean Validation |
| `javax.persistence.Entity` | `jakarta.persistence.Entity` | JPA |
| `javax.annotation.PostConstruct` | `jakarta.annotation.PostConstruct` | Lifecycle annotation |

**Không thay thế toàn bộ `javax.` bằng `jakarta.` một cách mù quáng.** Các API thuộc Java SE như `javax.crypto`, `javax.net`, `javax.xml`, `javax.management` không cùng quy tắc chuyển đổi. Chỉ sửa những API thực sự đã chuyển sang Jakarta EE và căn cứ vào bản thư viện đang dùng.

Sự thay đổi có ba hệ quả:

- **Tương thích mã nguồn:** import `javax.servlet.*` không biên dịch được trong dự án chỉ có `jakarta.servlet-api`; phải sửa mã nguồn và các type liên quan.
- **Tương thích nhị phân:** một thư viện JAR biên dịch với Servlet `javax` vẫn tham chiếu bytecode đến `javax/servlet/...`; chỉ đổi import của *ứng dụng* chưa làm thư viện đó tương thích. Cần bản thư viện được build cho Jakarta hoặc chuyển đổi artifact một cách có kiểm chứng.
- **Tương thích lúc chạy:** container dựa trên Jakarta không cung cấp Servlet kiểu `javax` để ứng dụng Spring MVC mới sử dụng; có thể gặp `ClassNotFoundException`, `NoClassDefFoundError`, lỗi khởi tạo Servlet/filter hoặc không triển khai được WAR.

Công cụ migration của Tomcat có thể giúp chuyển namespace ở artifact cũ trong một số trường hợp, nhưng không thay thế việc kiểm tra API bị xóa, thay đổi hành vi, thư viện bên thứ ba, cấu hình triển khai và kiểm thử tích hợp.

## 5. Ví dụ chạy thực tế: Spring Boot 3.5 và Jakarta Servlet

Ví dụ sau dùng **Java 17+, Spring Boot 3.5.16**, Maven và `spring-boot-starter-web`. Boot quản lý Spring Framework cùng Tomcat nhúng tương thích; không phải tự thêm một phiên bản `servlet-api` tùy ý. Ứng dụng trả về phiên bản Servlet mà container đang báo.

**Cấu trúc dự án:**

```text
servlet-compat/
├── pom.xml
└── src/main/java/demo/
    ├── WebApplication.java
    └── ServletInfoController.java
```

**`pom.xml`:**

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
    <groupId>demo</groupId>
    <artifactId>servlet-compat</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
```

**`src/main/java/demo/WebApplication.java`:**

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebApplication.class, args);
    }
}
```

**`src/main/java/demo/ServletInfoController.java`:**

```java
package demo;

import jakarta.servlet.ServletContext;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ServletInfoController {
    @GetMapping("/api/servlet")
    public String servletVersion(HttpServletRequest request) {
        ServletContext context = request.getServletContext();
        return "Servlet " + context.getMajorVersion()
                + "." + context.getMinorVersion();
    }
}
```

**Chạy khi đã cài JDK 17+ và Maven:**

```bash
mvn spring-boot:run
```

Ở terminal khác:

```bash
curl -s http://localhost:8080/api/servlet
```

Kết quả HTTP body với **Tomcat 10.1 nhúng mặc định của Boot 3.5**:

```text
Servlet 6.0
```

Trên Windows PowerShell có thể dùng `curl.exe` thay cho `curl`. Kết quả đang phản ánh **Servlet specification của container**, không phải chuỗi phiên bản Spring Framework hoặc phiên bản JDK. Nếu đổi sang container khác, phản hồi có thể khác.

**Thử lỗi có chủ đích:** đổi dòng import trong controller thành `import javax.servlet.http.HttpServletRequest;` trong khi vẫn dùng dependency Boot 3.5 ở trên. Dự án không có kiểu đó trên compile classpath và báo lỗi biên dịch liên quan package `javax.servlet.http`. Cách sửa là dùng `jakarta.servlet.http.HttpServletRequest` như ví dụ, không thêm JAR `javax.servlet-api` để che lỗi.

## 6. Spring Framework, Spring Boot và Servlet container không phải cùng một phiên bản

- **Spring Framework** cung cấp `spring-web`, `spring-webmvc`, IoC, transaction, v.v. Framework không tự quyết định phiên bản Tomcat nhúng của một dự án bất kỳ.
- **Spring Boot** là tầng cấu hình và quản lý dependencies, starters, auto-configuration, packaging. BOM của Boot quyết định các phiên bản Spring và container nhúng được kiểm thử cùng nhau.
- **Servlet API** là các interface/class tiêu chuẩn mà mã ứng dụng có thể biên dịch theo.
- **Servlet container** cung cấp implementation khi chạy, sở hữu vòng đời request/response, servlet và filter.

Trong **Boot executable JAR**, `spring-boot-starter-web` kéo vào container nhúng được quản lý (mặc định thường là Tomcat). Với **WAR triển khai lên container bên ngoài**, container đích phải đáp ứng mức Servlet mà thế hệ Spring yêu cầu; đồng thời packaging phải tránh đóng gói trùng các lớp/container implementation không phù hợp.

Đừng kết luận “đã dùng Java 21 nên Tomcat 9 chạy được Spring 6”. Java đủ mới chỉ giải quyết một điều kiện; Tomcat 9 vẫn cung cấp `javax.servlet`/Servlet 4.0 nên không thỏa yêu cầu Jakarta Servlet của Spring 6.

## 7. Chọn phiên bản khi bắt đầu và khi nâng cấp

### Tình huống A: ứng dụng Spring Boot 2.7 + Tomcat 9 hiện hữu

Bộ này thuộc thế hệ `javax.servlet.*`. Khi chuyển sang Boot 3.x, cần **cùng lúc** nâng yêu cầu JDK lên 17+, chuyển những API Java EE liên quan sang `jakarta.*`, chọn thư viện hỗ trợ Jakarta và kiểm tra container. Chỉ nâng Tomcat từ 9 sang 10.1 mà vẫn giữ WAR `javax` cũ không phải là nâng cấp tương thích hoàn chỉnh.

### Tình huống B: ứng dụng Boot 3.5 + Tomcat 10.1

Đây là tổ hợp hợp lệ: Spring 6.2 + Java 17+ + Jakarta Servlet 6.0 (mức Spring 6 tối thiểu là Servlet 5.0). Nếu triển khai WAR ra ngoài, cần kiểm tra version container và các dependency thực tế, không dựa vào việc compile trên máy cá nhân đã thành công.

### Tình huống C: muốn chuyển từ Boot 3.x sang Boot 4.x

Boot 4.x chuyển sang Spring 7, sử dụng Jakarta EE 11/Servlet **6.1+**. Nếu trước đó đang chạy Tomcat 10.1 (Servlet 6.0), phải chọn container đáp ứng Servlet 6.1, chẳng hạn Tomcat 11; đồng thời rà các thay đổi Spring/Boot và thư viện liên quan. Namespace vẫn là `jakarta.*`, nhưng **cùng namespace không bảo đảm cùng phiên bản API**.

### Tình huống D: thư viện web nội bộ vẫn import `javax.servlet.Filter`

Với Spring 6+/Boot 3+, hãy nâng hoặc rebuild thư viện bằng API Jakarta phù hợp. Khi xuất bản thư viện, xác định rõ biến thể hỗ trợ `javax` hay `jakarta`, khai báo dependency API thích hợp và kiểm thử với container đích. Một thư viện nhắm cả hai thế hệ có thể cần hai artifact/module hoặc một lớp thích nghi rõ ràng; Java không coi hai interface này là một.

## 8. Quy trình kiểm tra tương thích thực tế

1. **Ghi bộ phiên bản hiện tại:** `java -version`; phiên bản Boot/Framework trong `pom.xml` hoặc `build.gradle`; loại JAR/WAR; phiên bản container thực tế.
2. **Xác nhận dependency tree:** với Maven có thể dùng `mvn dependency:tree` để xem bản Spring, Tomcat và các JAR Servlet; với Gradle dùng `./gradlew dependencies --configuration runtimeClasspath`, hoặc `dependencyInsight` cho một dependency cụ thể.
3. **Kiểm tra namespace trong mã và dependencies:** tìm `javax.servlet`, `javax.validation`, `javax.persistence`, các implement `Filter`/`Servlet`, listener, JSP/tag library, framework tích hợp và annotation cũ. Chỉ chuyển những package có mapping thực sự.
4. **Đọc baseline từ tài liệu của đúng dòng Spring/Boot:** mức Java, Servlet, Jakarta EE và danh sách container được hỗ trợ. Đừng ghép ngẫu nhiên một bản Spring mới với Boot BOM cũ.
5. **Build sạch và chạy kiểm thử:** kiểm thử compile, khởi động context, endpoint HTTP, filter/security, serialization, validation, error handling; nếu deploy WAR, thử trên **đúng server đích**.
6. **Kiểm tra HTTP contract sau migration:** đường dẫn, method, status code, header, JSON, CORS, xác thực. Có thể giữ contract đối với client ngay cả khi thay đổi nền tảng Servlet bên trong, nhưng phải chứng minh qua kiểm thử.

Lệnh chẩn đoán ví dụ (trong dự án Maven ở mục 5):

```bash
java -version
mvn dependency:tree -Dincludes=org.springframework:spring-webmvc
mvn dependency:tree -Dincludes=org.apache.tomcat.embed:tomcat-embed-core
mvn dependency:tree -Dincludes=jakarta.servlet:jakarta.servlet-api
```

```bash
# Gradle: chạy tại dự án có Gradle wrapper
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency tomcat-embed-core --configuration runtimeClasspath
```

Không phải lúc nào `jakarta.servlet-api` cũng hiện thành dependency trực tiếp trong runtime tree: implementation Servlet có thể được cung cấp qua container, và scope/classpath khác nhau khi compile, runtime hoặc triển khai WAR. Vì vậy phải xem toàn bộ cấu hình dependency và môi trường chạy.

## 9. Các lỗi thường gặp và hướng xử lý

| Biểu hiện | Nguyên nhân khả dĩ | Cách kiểm tra và sửa |
| --- | --- | --- |
| `package javax.servlet.http does not exist` với Boot 3 | Mã vẫn dùng namespace trước Jakarta EE 9 | Đổi đúng API sang `jakarta.servlet.http` và cập nhật thư viện liên quan. |
| `NoClassDefFoundError: javax/servlet/Filter` | Một JAR cũ được build cho `javax.servlet` | Xác định JAR qua stack trace/dependency tree, nâng lên bản hỗ trợ Jakarta. |
| Triển khai Spring 6 WAR lên Tomcat 9 thất bại | Container chỉ có Servlet 4.0/`javax` | Chọn container tương thích Jakarta Servlet, kiểm tra cấu hình WAR. |
| Triển khai Spring 7 trên Tomcat 10.1 thất bại | Tomcat 10.1 triển khai Servlet 6.0, thấp hơn baseline 6.1 | Chọn container Servlet 6.1+ như Tomcat 11. |
| `UnsupportedClassVersionError` | JVM chạy thấp hơn bytecode Java dùng để build | Kiểm tra `java -version` của **runtime**, compiler target và Java baseline của framework. |
| `NoSuchMethodError` hoặc `AbstractMethodError` | API/implementation hay thư viện bất đồng phiên bản | Phân tích classpath, BOM, dependency overrides; đồng bộ bằng tập phiên bản được hỗ trợ. |
| Code compile nhưng request sai sau nâng cấp | Thay đổi cấu hình routing/filter/converter/behavior | Dùng kiểm thử integration và so sánh status/header/body giữa các phiên bản. |

**Quy tắc tránh lỗi:** không tùy tiện thêm cả `javax.servlet-api` và `jakarta.servlet-api` để “hỗ trợ mọi thứ”. Hai bộ kiểu không biến đổi lẫn nhau; classpath chứa cả hai có thể chỉ che dấu sự không tương thích của thư viện.

## 10. Phân biệt các loại tương thích

**API nguồn (source compatibility)** nói tới việc mã Java còn biên dịch với phiên bản API mới hay không. **Binary compatibility** nói tới bytecode/JAR đã build có còn liên kết được các class/method khi chạy hay không. **Runtime/platform compatibility** bao gồm JVM, Servlet container và các implementation thực tế. **HTTP/API contract compatibility** là cam kết với client qua URL, status, header, body; nó không buộc backend phải giữ cùng Servlet namespace.

Ví dụ: nâng từ Boot 2.7 lên 3.5 có thể cần sửa import Java và thay các thư viện `javax` để build/chạy được, nhưng endpoint `GET /api/users` vẫn có thể trả JSON và status giống hệt đối với client. Mặt khác, build thành công sau khi đổi namespace cũng chưa chứng minh filter, security, serialization hay lỗi HTTP giữ nguyên hành vi.

## 11. Tự kiểm tra hiểu bài

- Một dự án Spring Framework 6.2 biên dịch bằng Java 21 có deploy lên Tomcat 9 được không? **Không**: Tomcat 9 là Servlet 4.0/`javax`, khác mức Jakarta Servlet 5.0+ mà Spring 6 cần.
- Vì sao Boot 3.5 có thể trả `Servlet 6.0` dù bảng nói Spring 6 yêu cầu Servlet 5.0+? Vì **5.0+ là mức tối thiểu**, còn Tomcat 10.1 nhúng triển khai Servlet 6.0.
- Đã đổi `javax.servlet` sang `jakarta.servlet` rồi thì có thể giữ mọi JAR cũ không? **Không**: JAR đã biên dịch tham chiếu tên class và method riêng; cần kiểm tra và nâng dependency.
- Spring 7 và Spring 6 cùng dùng `jakarta.*` có chạy trên cùng Tomcat 10.1 không? **Không thể suy ra như vậy**: Spring 7 có baseline Servlet 6.1, trong khi Tomcat 10.1 là 6.0.
- Có nên đổi `javax.crypto.Cipher` thành `jakarta.crypto.Cipher`? **Không**: `javax.crypto` thuộc Java SE, không nằm trong lần đổi namespace Servlet/Jakarta EE.

## 12. Nguồn tài liệu chính thức và cách dùng

Các bảng baseline và ví dụ được xây dựng theo tài liệu phát hành hiện hành tại thời điểm soạn bài. Khi nâng một bản vá/milestone mới, ưu tiên tài liệu của **đúng phiên bản** đang triển khai:

- [Spring Framework Versions — JDK/Jakarta EE baselines](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions).
- [Spring Framework Overview — chuyển từ Java EE sang Jakarta EE](https://docs.spring.io/spring-framework/reference/overview.html).
- [Spring Web MVC và DispatcherServlet](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html).
- [Spring Boot 3.5 System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html).
- [Spring Boot 4.1 System Requirements](https://docs.spring.io/spring-boot/system-requirements.html).
- [Apache Tomcat: Which Version Do I Want?](https://tomcat.apache.org/whichversion.html).
- [Jakarta Servlet 6.1 specification](https://jakarta.ee/specifications/servlet/6.1/).

**Nguyên tắc lựa chọn:** luôn kiểm tra **JDK + Spring Framework/Boot + Servlet specification + container + dependencies của ứng dụng** như một bộ tương thích thống nhất.