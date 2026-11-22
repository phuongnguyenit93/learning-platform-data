
# Phân biệt bộ API với thư viện triển khai tương ứng

Trong quá trình nâng cấp Java, một lỗi dependency phổ biến là **có API để biên dịch nhưng không có thư viện triển khai ở runtime**, hoặc ngược lại: đóng gói nhiều implementation của cùng một API mà không biết implementation nào được chọn. Trường hợp khác là một API và implementation có vẻ cùng tên nhưng thuộc hai thế hệ không tương thích, chẳng hạn API theo namespace `javax.*` và implementation theo namespace `jakarta.*`.

Sự nhầm lẫn này có thể khiến ứng dụng:

- Biên dịch thành công nhưng gặp `ClassNotFoundException`, `NoClassDefFoundError` hoặc lỗi không tìm thấy provider khi khởi động.
- Gặp `NoSuchMethodError` hoặc `AbstractMethodError` khi API và implementation không tương thích về nhị phân.
- Có nhiều provider được phát hiện, kết quả phụ thuộc classpath, thứ tự module hoặc cấu hình.
- Đóng gói thừa container implementation gây xung đột class loader khi triển khai WAR.
- Chạy được trên máy phát triển nhưng thất bại trong Docker image, server hoặc JDK mới.
- Bị phụ thuộc ngầm vào một implementation làm việc thay thế thư viện trở nên rất khó.

Bài học thuộc **Java Advance Compatibility Migration**, phần **Quản lý dependency**, tập trung vào cách nhận diện và quản lý ranh giới **bộ API (contract)** với **thư viện triển khai (implementation/provider)** trong Java, Maven, Gradle, JPMS và môi trường triển khai thực tế.

## 1. API và implementation là hai vai trò khác nhau

**Bộ API** mô tả những kiểu, hợp đồng và điểm mở rộng mà mã ứng dụng dựa vào. Nó có thể chứa:

- Interface và abstract class.
- Annotation, enum và kiểu dữ liệu công khai.
- Method signatures, exception types và constant.
- Factory, bootstrap API hoặc registry để tìm implementation.
- Service Provider Interface (SPI), tức hợp đồng mà implementation phải tuân thủ.
- Metadata dành cho công cụ biên dịch hoặc runtime.

**Thư viện triển khai** cung cấp hành vi cụ thể cho hợp đồng đó, chẳng hạn:

- Kết nối database thực sự.
- Render servlet request/response bằng web container.
- Ghi log qua một backend.
- Thực hiện validation cho một đối tượng.
- Quản lý persistence context, SQL và transaction của JPA.
- Serialize đối tượng bằng engine JAXB.

Một ví dụ Java tối giản:

~~~java
package com.example.api;

public interface MessageSender {
    void send(String destination, String message);
}
~~~

Implementation:

~~~java
package com.example.impl;

import com.example.api.MessageSender;

public final class SmtpMessageSender implements MessageSender {
    @Override
    public void send(String destination, String message) {
        // Kết nối SMTP, xác thực và gửi dữ liệu.
    }
}
~~~

Module sử dụng API có thể chỉ cần biết `MessageSender`. Nhưng ở runtime phải có một instance cụ thể của `SmtpMessageSender` hoặc implementation tương đương, được cung cấp qua dependency injection, factory hoặc cấu hình.

### 1.1. Sơ đồ phụ thuộc

~~~mermaid
flowchart TD
    A["Application / Consumer"] --> B["API / Contract"]
    C["Implementation A"] --> B
    D["Implementation B"] --> B
    E["Runtime wiring / SPI / DI"] --> C
    E --> D
    A --> E
~~~

Trong thực tế, consumer có thể tương tác với factory nằm trong API và được nối với implementation ở runtime. Điều quan trọng là **biết ai cung cấp contract, ai cung cấp hành vi, và ai chọn provider**.

### 1.2. Một API artifact không nhất thiết chỉ có interface

Tên “API” không có nghĩa JAR chỉ chứa interface. Nó có thể có class tiện ích, default method, factory hoặc một số implementation cơ bản. Tương tự, một “implementation” artifact có thể chứa public type cho cấu hình.

Phân biệt dựa trên **vai trò trong kiến trúc và hợp đồng phát hành**, không chỉ dựa vào tên file `*-api.jar` hay `*-impl.jar`.

### 1.3. API Java SE khác API độc lập trong dependency

Một số API nằm trong JDK, ví dụ `java.sql` cung cấp `Connection`, `DriverManager` và `DataSource`. Chúng không cần một Maven dependency riêng khi JDK đã cung cấp module tương ứng.

Các API khác là dependency ngoài JDK, ví dụ những API thuộc họ Jakarta EE. Một số API Java EE từng có mặt trong các JDK cũ đã được loại khỏi JDK 11 theo quá trình modularization. Khi migrate, cần xác định đúng **API nào là một phần Java SE**, API nào phải khai báo ngoài và implementation nào runtime hoặc server sẽ cung cấp.

## 2. Bốn trường hợp dependency cần phân biệt

| Tình huống | Có API để compile? | Có implementation ở runtime? | Kết quả |
|---|---|---|---|
| Đúng contract, đúng provider | Có | Có | Có thể chạy nếu version/config phù hợp |
| Chỉ có API | Có | Không | Compile thường đạt; bootstrap hoặc chức năng thực tế thất bại |
| Chỉ có implementation | Có thể có/không | Có | Compile có thể thiếu public API; phụ thuộc packaging của implementation |
| Nhiều provider | Có | Nhiều | Có thể chạy, chọn sai provider hoặc phát sinh xung đột |
| API và provider khác thế hệ | Có | Có nhưng không tương thích | Linkage/configuration/runtime errors |
| Container đã cung cấp implementation, ứng dụng đóng thêm | Có | Trùng hoặc conflict | Class loader, version và service resolution có thể lỗi |

Không thể kết luận “đã đủ dependency” bằng cách chỉ nhìn sự có mặt của một JAR tên đúng. Cần kiểm tra **runtimeClasspath và artifact đóng gói**, nơi loader thực sự tìm API/provider.

## 3. Một số cặp API — implementation thường gặp

Các ví dụ dưới đây minh họa **vai trò**. Version cụ thể và khả năng tương thích phải được xác nhận theo tài liệu release của từng dự án, không được suy ra rằng mọi artifact mang tên giống nhau luôn ghép được.

| Nhu cầu | API/hợp đồng | Implementation hoặc runtime thường gặp | Ghi chú |
|---|---|---|---|
| Servlet | Jakarta Servlet API | Servlet container như Tomcat, Jetty | Container thường cung cấp API và engine khi deploy WAR |
| JPA | Jakarta Persistence API | Hibernate ORM, EclipseLink | Provider thực thi persistence/SQL |
| Bean Validation | Jakarta Validation API | Hibernate Validator | Provider thực thi constraint validation |
| CDI | Jakarta CDI API | Weld, OpenWebBeans | Có thể do application server cấp |
| JAXB | Jakarta XML Binding API | GlassFish JAXB runtime hoặc implementation tương thích | Phải đúng thế hệ namespace |
| Jakarta Mail | Jakarta Mail API | Jakarta Mail/Angus Mail implementation phù hợp | Cần xem provider và phiên bản |
| JAX-WS | Jakarta XML Web Services API | Metro hoặc runtime phù hợp | Không chỉ thêm API sau JDK 11 |
| Logging facade | SLF4J API | Logback, SLF4J provider thích hợp | Cần khớp major line SLF4J |
| JDBC | Java SE `java.sql` API | JDBC driver của database vendor | Driver thường được phát hiện ở runtime |
| JSON Processing (JSON-P) | Jakarta JSON Processing API | JSON-P provider phù hợp | API khác JSON-B |
| JSON Binding (JSON-B) | Jakarta JSON Binding API | Yasson hoặc provider tương ứng | Có thể phụ thuộc JSON-P implementation |
| Cryptography | JCA/JCE engine API trong JDK | Security provider phần mềm, HSM/PKCS#11 | Provider có thể do JDK hoặc vendor cung cấp |

Bảng này **không phải danh sách phiên bản dependency để copy vào production**. Cách ghép chính xác còn phụ thuộc Java baseline, framework, container, classpath/module path và cấu hình triển khai.

## 4. Ví dụ 1: Servlet API và servlet container

Giả sử viết một servlet:

~~~java
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import java.io.IOException;

public class HealthServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response) throws IOException {
        response.setContentType("text/plain; charset=UTF-8");
        response.getWriter().write("OK");
    }
}
~~~

Các class `HttpServlet`, `HttpServletRequest` và `HttpServletResponse` thuộc **Servlet API**. Nhưng bản thân API không mở cổng HTTP, phân luồng request, quản lý servlet lifecycle hay xử lý connector. Đó là công việc của **Servlet container**.

### 4.1. WAR triển khai trên container ngoài

Với mô hình deploy một WAR vào Tomcat/Jetty tương thích, container cung cấp Servlet API và implementation. Vì vậy, dependency Servlet API thường được đánh dấu **provided** hoặc **compileOnly** trong cấu hình build, tránh đóng gói một bản API trùng/không phù hợp vào `WEB-INF/lib`.

Ví dụ Maven mang tính minh họa:

~~~xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <version>VERSION_MATCHING_CONTAINER</version>
    <scope>provided</scope>
</dependency>
~~~

`VERSION_MATCHING_CONTAINER` chỉ là placeholder thể hiện yêu cầu chọn version tương thích, không phải version thực để Maven resolve.

Nếu đóng nhầm một implementation/container khác vào WAR, một container có thể gặp:

- Trùng API class ở các class loader.
- Version của servlet API không khớp container.
- `ClassCastException` dù tên class giống nhau nhưng đến từ loader khác.
- Lỗi linkage hoặc service initialization.
- Conflict với thư viện đã được server quản lý.

### 4.2. Executable JAR có embedded server

Với ứng dụng dùng embedded Tomcat/Jetty, runtime dependency sẽ khác: ứng dụng thường **đóng gói server implementation** để tự khởi động và nhận HTTP request.

Không được máy móc đặt tất cả servlet-related dependency thành provided trong ứng dụng standalone. Hãy hỏi:

1. Runtime là external container hay embedded container?
2. Ai sở hữu servlet engine?
3. Dependency nào được đóng gói vào JAR/WAR?
4. Phiên bản servlet API được engine hỗ trợ?
5. Có class loader separation hoặc module path không?

Một cấu hình đúng với WAR truyền thống có thể sai hoàn toàn khi chuyển sang executable JAR.

### 4.3. javax.servlet và jakarta.servlet không tương đương

Các thế hệ Servlet cũ dùng package `javax.servlet.*`; các API Jakarta mới dùng `jakarta.servlet.*`. Đây là hai **tên kiểu khác nhau ở bytecode level**.

Không thể kỳ vọng implementation cho `jakarta.servlet.*` tự động xử lý một ứng dụng đã biên dịch với `javax.servlet.*` chỉ vì đều gọi là “Servlet API”. Khi migration, cần phối hợp cả source/import, API artifact, implementation/container và framework phù hợp.

## 5. Ví dụ 2: Jakarta Persistence API và JPA provider

Một entity có thể khai báo bằng annotation JPA:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class Customer {
    @Id
    private Long id;

    private String name;

    protected Customer() {
    }
}
~~~

Những annotation như `@Entity` và `@Id` thuộc **Jakarta Persistence API**. Chúng định nghĩa metadata, nhưng không tự thực hiện SQL, dirty checking, caching hay transaction handling.

Một provider như Hibernate ORM hoặc EclipseLink có thể đảm nhiệm những chức năng đó.

### 5.1. API chỉ đủ cho compilation

Ví dụ:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.Persistence;

EntityManager em =
        Persistence.createEntityManagerFactory("orders")
                .createEntityManager();
~~~

Lời gọi có thể được biên dịch khi có API. Ở runtime, nếu thiếu provider tương thích hoặc cấu hình `persistence.xml`/container integration cần thiết, việc bootstrap sẽ thất bại.

Nguyên nhân có thể là:

- Không có provider runtime.
- Provider không được đăng ký hoặc không được tìm thấy.
- Provider có nhưng lệch generation của API.
- Datasource/driver không có.
- Cấu hình `persistence.xml` sai hoặc không nằm trong artifact.
- Provider hoạt động nhưng không hỗ trợ version Java/class-file mới.
- Module access cho entity reflection không được cấu hình đúng.

Để sửa, không chỉ thêm ngẫu nhiên JAR tên `*-impl`. Cần xem **provider resolution path**, dependency graph và môi trường thực tế.

### 5.2. Framework starter có thể đã mang provider

Một starter/framework platform có thể transitively kéo API, implementation và các dependency liên quan. Khi đó, thêm API hoặc provider trực tiếp không đúng phiên bản có thể gây conflict với dependency management của framework.

Cần xem:

- BOM/platform đang quản lý những version nào.
- Provider thực tế được resolve là gì.
- Starter có loại trừ provider khác không.
- Có nhiều JPA providers cùng tồn tại không.
- Có application server nào đã cấp runtime không.

**Không coi dependency không được khai báo trực tiếp là dependency không tồn tại.** Transitive dependency vẫn có mặt trên classpath nếu không bị exclude.

## 6. Ví dụ 3: Jakarta Validation API và validation provider

Một DTO có annotation:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public record CreateUser(
        @NotBlank String name,
        @Email String email) {
}
~~~

`@NotBlank` và `@Email` là các API/metadata constraint. Nhưng chỉ có annotation không có nghĩa validation tự chạy.

Ví dụ runtime:

~~~java
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

public class ValidateExample {
    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            var violations = validator.validate(
                    new CreateUser("", "bad-email"));

            System.out.println(violations.size());
        }
    }
}
~~~

Mô hình sử dụng:

1. API cho phép import annotation và gọi `Validation`.
2. Provider runtime thực thi các constraint.
3. Bootstrap mechanism xác định provider.
4. Framework như Spring có thể tự tích hợp validator và vòng đời phù hợp.

Nếu thiếu provider, mã DTO vẫn có thể compile, nhưng bootstrap có thể ném `ValidationException`, tùy tình huống cụ thể.

### 6.1. Khi nào cần implementation trực tiếp?

- Nếu ứng dụng standalone gọi `Validation.buildDefaultValidatorFactory()`, cần provider runtime phù hợp.
- Nếu application server đã cung cấp Bean Validation, cần xem mô hình classloading và dependency scope.
- Nếu framework starter đã có provider, không thêm bản implementation thứ hai chỉ vì thấy API dependency.

### 6.2. Annotation không có hiệu ứng nếu không có engine

Có `@Email` trên field không tự khiến một phép gọi setter hay constructor từ chối input. Validation chỉ xảy ra khi engine/framework được cấu hình để thực hiện.

Cần test một **constraint thực sự bị vi phạm**, không chỉ test việc đọc được annotation qua reflection.

## 7. Ví dụ 4: SLF4J API và logging implementation

SLF4J là ví dụ trực quan về mô hình facade và provider.

Mã ứng dụng:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class OrderService {
    private static final Logger log =
            LoggerFactory.getLogger(OrderService.class);

    public void process(long orderId) {
        log.info("Processing order {}", orderId);
    }
}
~~~

Ứng dụng sử dụng **SLF4J API**, nhưng việc log đi tới console, file, JSON sink hoặc hệ thống giám sát phụ thuộc **logging provider/backend**.

Một triển khai phổ biến có thể dùng Logback; một dự án khác dùng Log4j 2 qua binding/provider tương thích.

### 7.1. Thiếu provider

Chỉ có `slf4j-api` có thể làm code compile và chạy nhưng log không được xử lý bởi backend thực như mong đợi, hoặc runtime phát cảnh báo và dùng implementation không ghi log.

Kết quả cụ thể phụ thuộc dòng SLF4J:

- SLF4J 1.7 dùng cơ chế binding riêng.
- SLF4J 2.x dùng service provider mechanism.
- Một binding/provider cho generation không tương thích có thể không được nhận.

Vì vậy, **đừng trộn bừa binding SLF4J 1.7 với runtime SLF4J 2.x** và kỳ vọng nó được lựa chọn.

### 7.2. Có nhiều provider

Khi nhiều SLF4J providers khả dụng, runtime có thể cảnh báo và lựa chọn một provider; kết quả vận hành trở nên khó dự đoán nếu chỉ dựa vào thứ tự classpath.

Giải pháp là:

1. Xác định backend logging được hệ thống chọn.
2. Duy trì đúng provider/binding cần thiết.
3. Exclude provider không mong muốn từ dependency bắc cầu.
4. Test log thực sự được ghi và gửi tới đúng destination.
5. Kiểm tra cấu hình logging trong artifact cuối cùng.

### 7.3. Bridge và vòng lặp chuyển tiếp

Một số thư viện dùng Java Util Logging (JUL), Log4j API hoặc SLF4J. Các bridge có thể chuyển event từ framework này sang framework khác.

Nếu cấu hình bridge vòng tròn, ví dụ từ A sang B rồi từ B về A, có thể gây recursion, lặp log hoặc các lỗi nghiêm trọng. Do đó, đừng thêm mọi bridge “để cho chắc”.

Cần vẽ đúng hướng luồng logging và phân biệt:

- API mà source gọi.
- Backend thực sự ghi.
- Bridge dùng để thích ứng API khác.
- Provider/binding thực thi giao tiếp với backend.

## 8. Ví dụ 5: JDBC API và driver implementation

Trong Java SE, `java.sql` có các interface:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;

Connection connection =
        DriverManager.getConnection(
                "jdbc:vendor://db.example:5432/app",
                "username",
                "password");
~~~

**JDBC API** mô tả `Connection`, `PreparedStatement`, `ResultSet` và các hợp đồng khác. **JDBC driver** của database vendor triển khai cách nói chuyện với DB.

Ứng dụng có thể biên dịch chỉ với JDK, nhưng `DriverManager.getConnection(...)` sẽ không hoạt động nếu không có driver phù hợp hoặc URL/config hợp lệ.

### 8.1. Phát hiện driver

JDBC hiện đại có cơ chế tìm driver dựa trên service provider registration của driver JAR. Vì vậy, với driver phù hợp, ứng dụng không nhất thiết cần gọi thủ công:

~~~java
Class.forName("com.vendor.jdbc.Driver");
~~~

Tuy nhiên, driver loading thực tế vẫn phụ thuộc classpath, module path và cơ chế class loader của môi trường. Một số framework hoặc môi trường ứng dụng có cách quản lý datasource riêng.

### 8.2. Driver có thể là runtime-only

Nếu source chỉ gọi standard JDBC API, có thể không cần import class của vendor driver khi compile. Khi đó, JAR driver có thể được khai báo như dependency chỉ dùng ở runtime, tùy build tool và framework.

Ví dụ Gradle:

~~~groovy
dependencies {
    runtimeOnly("com.vendor:jdbc-driver:VERSION")
}
~~~

`com.vendor:jdbc-driver:VERSION` chỉ là placeholder. Một driver thật phải được chọn theo database, Java baseline, license và version tương thích.

Nếu source import type riêng của vendor, driver có thể cần có ở compile classpath; nhưng đó cũng làm ứng dụng phụ thuộc vào implementation-specific API.

### 8.3. Driver đúng chưa chắc database connection thành công

Các lỗi khác nhau:

- `No suitable driver`: driver không được tìm thấy/không nhận URL.
- Authentication failure: driver có nhưng credentials/policy sai.
- TLS handshake error: driver có nhưng cấu hình certificate/protocol không tương thích.
- `NoSuchMethodError`: driver hoặc transitive dependency lệch phiên bản.
- Unsupported class file: driver được biên dịch cho JDK mới hơn runtime.

Đừng gộp mọi lỗi JDBC thành “thiếu JDBC API”.

## 9. Ví dụ 6: JAXB và các API không còn nằm trong JDK mới

Ở một số JDK cũ, các module Java EE-related như JAXB/JAX-WS từng được cung cấp theo cơ chế của JDK. Trong JDK 11, các module Java EE và CORBA liên quan đã bị loại bỏ (JEP 320).

Hậu quả: mã từng compile/run trên JDK cũ có thể không còn tìm thấy các kiểu JAXB hoặc bootstrap runtime khi chuyển lên JDK 11+.

Ví dụ consumer JAXB:

~~~java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.Marshaller;

JAXBContext context =
        JAXBContext.newInstance(Customer.class);

Marshaller marshaller =
        context.createMarshaller();

marshaller.marshal(customer, System.out);
~~~

Khi dùng thế hệ Jakarta, cần **API cùng namespace** và **implementation phù hợp**. Chỉ thêm API artifact có thể cho phép compile nhưng `JAXBContext.newInstance(...)` thất bại vì không có runtime provider.

### 9.1. Hai vấn đề độc lập khi migrate JAXB

**Vấn đề A — thư viện không còn do JDK cấp:** phải khai báo dependency bên ngoài thay vì phụ thuộc vào module đã bị loại.

**Vấn đề B — namespace/generation:** nhiều API cũ là `javax.xml.bind.*`, trong khi thế hệ Jakarta mới là `jakarta.xml.bind.*`. Chuyển namespace đòi hỏi kiểm tra source, annotation, provider và framework, không chỉ đổi groupId của dependency.

Không nên trộn:

- Source import `javax.xml.bind.*`.
- API `jakarta.xml.bind.*`.
- Runtime implementation của thế hệ khác.

Nhiều tình huống lỗi có thể trông như thiếu class hoặc không tìm thấy provider dù JAR “JAXB” đã có mặt.

### 9.2. API và runtime là hai artifact có thể tách biệt

Ví dụ Maven minh họa:

~~~xml
<dependency>
    <groupId>jakarta.xml.bind</groupId>
    <artifactId>jakarta.xml.bind-api</artifactId>
    <version>COMPATIBLE_API_VERSION</version>
</dependency>

<dependency>
    <groupId>org.glassfish.jaxb</groupId>
    <artifactId>jaxb-runtime</artifactId>
    <version>COMPATIBLE_RUNTIME_VERSION</version>
    <scope>runtime</scope>
</dependency>
~~~

Các giá trị `COMPATIBLE_*` là placeholder, không phải literal để build trực tiếp. Chọn version dựa trên compatibility matrix của runtime/framework/JDK mục tiêu.

Nếu source hoặc annotation processor dùng implementation-specific type, scope chỉ runtime có thể không đủ; cần xác định đúng ranh giới code thực tế thay vì copy mẫu máy móc.

## 10. JAX-WS, Jakarta Mail, CDI và JSON providers

Để tránh những lỗi tương tự, có thể áp dụng cùng một bộ câu hỏi cho nhiều chuẩn Java:

### 10.1. JAX-WS

API cho web services dựa trên SOAP định nghĩa annotation và hợp đồng. Runtime tương ứng cần một implementation stack, ví dụ Metro trong những hệ thống dùng stack đó.

Sau khi các module Java EE không còn được JDK 11 cung cấp, chỉ thêm API và chờ server SOAP tự chạy thường không đủ. Cần xem:

- Runtime tạo và xử lý SOAP messages.
- HTTP transport integration.
- XML binding.
- Provider registration.
- Package namespace phù hợp.

### 10.2. Jakarta Mail

Các API kiểu `jakarta.mail.*` mô tả message, session, transport và các khái niệm. Implementation tương ứng phải cung cấp provider cho giao thức SMTP/IMAP/POP3 khi ứng dụng dùng.

Khi lỗi xảy ra, phải phân biệt:

- API chưa có.
- Implementation/provider chưa có.
- Provider đã có nhưng cấu hình giao thức/TLS/authentication sai.
- Khác thế hệ namespace `javax.mail` và `jakarta.mail`.

### 10.3. CDI

CDI API mô tả dependency injection contracts và annotation; runtime CDI như Weld hoặc OpenWebBeans được tích hợp theo kiến trúc triển khai.

Một Java application chạy trực tiếp `main` với annotation CDI không tự có container-managed injection nếu không bootstrap runtime CDI hoặc framework có hỗ trợ. Ngược lại, application server có thể đã cung cấp CDI, nên đóng thêm một runtime độc lập có thể không đúng.

### 10.4. JSON-P và JSON-B

JSON-P và JSON-B là hai bộ API khác nhau với vai trò khác nhau:

- JSON-P tập trung vào parsing/generation và mô hình JSON.
- JSON-B định nghĩa cách binding JSON với object Java.

Một runtime JSON-B có thể cần JSON-P implementation tương thích. Không nên thấy chữ “JSON” rồi coi một dependency là đủ cho mọi API.

Mỗi cặp cần xem engine/factory, provider detection và transitive dependency cụ thể.

## 11. Maven dependency scopes: API và runtime nằm ở đâu?

Một Maven project có thể có những scope sau:

| Scope | Vai trò chính | Lưu ý đối với API/implementation |
|---|---|---|
| `compile` | Có khi biên dịch và thường ở runtime/test classpath | Mặc định; có thể kéo transitively đến consumer |
| `provided` | Compile/test có dependency nhưng kỳ vọng runtime/container cung cấp | Thích hợp khi server đã quản lý API/implementation |
| `runtime` | Cần ở runtime/test, không cần để compile source | Phù hợp với driver/provider không được source import |
| `test` | Chỉ cho test | Implementation test không tự vào production artifact |
| `system` | Dependency qua đường dẫn local, ít portable | Thường nên tránh và quản lý artifact chuẩn hơn |
| `import` | Import BOM trong dependencyManagement | Quản lý version, không tự thêm JAR vào runtime |

Ví dụ khi deploy WAR lên container Servlet tương thích:

~~~xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <version>COMPATIBLE_VERSION</version>
    <scope>provided</scope>
</dependency>
~~~

Ví dụ runtime provider khi ứng dụng standalone:

~~~xml
<dependency>
    <groupId>example.group</groupId>
    <artifactId>example-implementation</artifactId>
    <version>COMPATIBLE_VERSION</version>
    <scope>runtime</scope>
</dependency>
~~~

`example.*` và `COMPATIBLE_VERSION` là placeholder.

### 11.1. provided không có nghĩa “không cần runtime”

Một sai lầm nguy hiểm là hiểu `provided` như “dependency không cần nữa”. Thực chất nó nói với build rằng **môi trường chạy bên ngoài sẽ cung cấp** thành phần đó. Nếu môi trường không cung cấp, ứng dụng có thể compile rồi lỗi runtime.

Ví dụ:

- WAR: Servlet container cung cấp Servlet API.
- Standalone JAR: nếu không có embedded server, chỉ scope provided có thể làm mất phần cần thiết khi chạy.
- App server: có thể cung cấp JPA/CDI/Validation; cần biết phiên bản thực tế.
- Test container: có thể mô phỏng môi trường, nhưng test trên máy local không đại diện hoàn toàn production.

### 11.2. BOM không phải implementation

Một BOM trong `dependencyManagement` xác định version hoặc constraint, không tự động tải và đưa mọi module của platform vào runtime.

Ví dụ:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>example.platform</groupId>
      <artifactId>example-bom</artifactId>
      <version>PLATFORM_VERSION</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
~~~

Sau khi import BOM, dự án vẫn cần khai báo các dependency phù hợp. Đừng coi “đã import BOM” là bằng chứng đã có provider.

### 11.3. Đánh giá dependency transitively

Một runtime implementation thường kéo API và thư viện trợ giúp theo dependency graph. Có trường hợp chỉ thêm implementation đã đủ cho compile và runtime vì API transitively đi theo. Nhưng đối với **public library API**, nên biểu diễn dependency contract rõ ràng thay vì phó mặc API availability cho implementation transitively.

Nếu viết thư viện `my-validation-extension` có public method nhận `jakarta.validation.Validator`, kiểu đó là một phần của public API của thư viện; scope truyền tới consumer phải được thiết kế để consumer compile được.

## 12. Gradle: api, implementation, compileOnly và runtimeOnly

Trong Gradle với `java-library` plugin, những configuration có ý nghĩa khác nhau:

| Configuration | Compiler của module hiện tại | Compiler của consumer | Runtime |
|---|---|---|---|
| `api` | Có | Có qua API dependency | Thường có |
| `implementation` | Có | Không được export như compile API cho consumer | Có |
| `compileOnly` | Có | Không tự được đưa tới consumer qua runtime | Không mặc định |
| `runtimeOnly` | Không | Không | Có |
| `testImplementation` | Có cho test | Không | Test |
| `testRuntimeOnly` | Không cho compile test | Không | Runtime của test |

Ví dụ một thư viện sử dụng API công khai và provider nội bộ:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    api("com.example:service-api:API_VERSION")
    implementation("com.example:service-helper:HELPER_VERSION")
    runtimeOnly("com.example:service-provider:PROVIDER_VERSION")
}
~~~

Đây chỉ là cú pháp minh họa bằng tọa độ placeholder.

### 12.1. Khi nào dùng api?

Nếu public method signature, superclass hoặc public annotation của thư viện chứa kiểu từ dependency, consumer có thể cần kiểu đó ở compile classpath.

~~~java
package com.example.library;

import com.example.contract.Task;

public interface TaskExecutor {
    void execute(Task task);
}
~~~

Nếu `Task` đến từ `service-api`, dependency mang kiểu đó cần được công bố phù hợp cho consumer. Trong Gradle `java-library`, `api(...)` thường là lựa chọn thích hợp.

### 12.2. Khi nào dùng implementation?

Nếu dependency chỉ phục vụ code nội bộ và không lộ qua contract public:

~~~java
public final class TaskExecutorImpl {
    private final InternalCodec codec = new InternalCodec();
}
~~~

thì `implementation(...)` giúp tránh lộ dependency như compile-time API của consumer. Dù vậy, dependency vẫn có thể hiện diện ở runtime.

### 12.3. Khi nào dùng compileOnly?

`compileOnly` dùng khi module cần type để compile nhưng **không tự mang JAR đó vào runtime**. Trường hợp thường gặp: API được application server/container cung cấp.

Không dùng `compileOnly` chỉ vì artifact được gọi là “API”. Nếu runtime không có artifact đó qua đường khác, consumer có thể thất bại khi nạp class, annotation hoặc interface.

### 12.4. Khi nào dùng runtimeOnly?

`runtimeOnly` phù hợp khi source không trực tiếp cần implementation class để compile, nhưng runtime cần provider hoặc driver. Ví dụ JDBC driver với mã chỉ dùng `java.sql`.

Nếu source import implementation-specific type hoặc khởi tạo provider class trực tiếp bằng `new`, cần compile dependency tương ứng; việc để `runtimeOnly` có thể gây compile error.

### 12.5. Java library phát hành metadata ra ngoài

Gradle có thể xuất metadata theo variant `apiElements` và `runtimeElements`. Khi publish, việc khai báo `api` và `implementation` chính xác giúp consumer nhận đúng compile và runtime dependencies.

Không nên viết thư viện public mà kiểm tra chỉ bằng cách chạy từ cùng repository. Cần thử một consumer độc lập sử dụng artifact đã publish hoặc bản snapshot để đảm bảo metadata dependency đến consumer đúng như dự kiến.

## 13. SPI: cơ chế nối API với provider

**Service Provider Interface (SPI)** là một hợp đồng để implementation đăng ký và được consumer tìm thấy mà không cần consumer import trực tiếp class implementation.

Trong Java SE, `java.util.ServiceLoader` là cơ chế phổ biến.

### 13.1. Định nghĩa service interface

~~~java
package com.example.spi;

public interface TextEncoder {
    String encode(String input);
}
~~~

### 13.2. Tạo implementation

~~~java
package com.example.impl;

import com.example.spi.TextEncoder;

public final class UppercaseEncoder implements TextEncoder {
    @Override
    public String encode(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

### 13.3. Đăng ký khi dùng classpath

Implementation JAR có thể chứa:

~~~text
META-INF/services/com.example.spi.TextEncoder
~~~

Nội dung file:

~~~text
com.example.impl.UppercaseEncoder
~~~

Consumer:

~~~java
import com.example.spi.TextEncoder;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        for (TextEncoder encoder :
                ServiceLoader.load(TextEncoder.class)) {
            System.out.println(encoder.encode("hello"));
        }
    }
}
~~~

Consumer compile với API, runtime cần implementation JAR và service descriptor. Nếu thiếu service file, provider có thể **tồn tại trong JAR nhưng không được tìm thấy**.

### 13.4. Named modules dùng provides/uses

Với Java Platform Module System, một implementation named module có thể khai báo:

~~~java
module com.example.encoder.impl {
    requires com.example.encoder.api;
    provides com.example.spi.TextEncoder
        with com.example.impl.UppercaseEncoder;
}
~~~

Consumer module có thể khai báo:

~~~java
module com.example.application {
    requires com.example.encoder.api;
    uses com.example.spi.TextEncoder;
}
~~~

Module API cần export package chứa `TextEncoder` để các module khác dùng. Việc triển khai còn phụ thuộc module path, resolution và layer được sử dụng.

Không nên mặc định một file `META-INF/services` đủ trong mọi thiết lập JPMS hoặc ngược lại mặc định `provides` tự giải quyết classpath packaging. Phải kiểm tra đúng cách chạy của artifact.

### 13.5. Một số lỗi của ServiceLoader

- `ServiceConfigurationError`: provider metadata sai, class không nạp được hoặc không thỏa điều kiện provider.
- Không tìm thấy provider: implementation không nằm trong runtime, descriptor bị mất hoặc module không được resolve.
- Nhiều provider: consumer cần policy chọn đúng một provider hoặc cho phép nhiều provider.
- Provider không tương thích: triển khai interface cũ có thể gặp linkage/error khi nạp hoặc gọi method.

Service discovery là một **hợp đồng runtime**, không phải chỉ là dependency có mặt trong POM.

## 14. Factory và dependency injection là cơ chế wiring khác SPI

Một API có thể khai báo factory:

~~~java
public interface Storage {
    void save(String key, byte[] value);
}
~~~

Ứng dụng có thể xây instance trực tiếp:

~~~java
Storage storage = new FileStorage(rootDirectory);
~~~

Hoặc inject:

~~~java
public final class BackupService {
    private final Storage storage;

    public BackupService(Storage storage) {
        this.storage = storage;
    }
}
~~~

Trong ví dụ thứ hai, một container DI hoặc bootstrap code có trách nhiệm cung cấp `Storage`.

Nếu chỉ có API và không đăng ký bean/implementation, hệ thống có thể khởi động lỗi hoặc không tạo được component. Đừng tìm `META-INF/services` nếu framework thực tế dùng DI bean registration; tương tự, đừng tìm DI registration nếu API bootstrap qua `ServiceLoader`.

### 14.1. Ba cách kết nối thường gặp

| Cách | Ai chọn implementation? | Cần kiểm tra gì? |
|---|---|---|
| Khởi tạo trực tiếp | Code ứng dụng | Compile dependency và constructor |
| Factory/Bootstrap | API hoặc cấu hình runtime | Provider implementation và factory resolution |
| ServiceLoader/SPI | Service discovery | Service files, module declarations, runtime path |
| Dependency injection | Container/framework | Bean definitions, scanning, scope và runtime |
| Application server | Server platform | API/provider version và deployment isolation |

Nhiều framework kết hợp nhiều cơ chế. Ví dụ DI container có thể dùng `ServiceLoader` trong bootstrap rồi cung cấp bean cho application.

## 15. Java module system và classpath/module path

Ở JVM hiện đại, cùng một dependency có thể được chạy trên **classpath** hoặc **module path**. Cơ chế truy cập và service discovery có những khác biệt.

### 15.1. API module và implementation module

Một ví dụ kiến trúc:

~~~text
com.example.contract
  exports com.example.contract

com.example.provider
  requires com.example.contract
  provides com.example.contract.Codec
      with com.example.provider.DefaultCodec

com.example.app
  requires com.example.contract
  uses com.example.contract.Codec
~~~

Consumer có thể chỉ yêu cầu module API. Nhưng runtime phải **resolve** implementation module, và service binding phải được cấu hình phù hợp.

Nếu tạo custom runtime bằng `jlink`, việc chỉ đưa API module vào image có thể không mang theo implementation. Tùy cách build image, có thể cần chỉ định provider module hoặc cơ chế service binding được hỗ trợ.

### 15.2. Automatic module không thay thế kiểm tra SPI

Một JAR được đưa lên module path nhưng không có `module-info.class` có thể trở thành automatic module. Tên module và đặc điểm module path không tự bảo đảm mọi service provider được chọn hoặc tương thích.

Cần kiểm tra:

- Tên module thực tế.
- `requires`, `exports` và `opens`.
- `uses` và `provides` khi có.
- Các dependency/module được resolve.
- Classpath/module path và class loader tương ứng.
- Reflection access nếu implementation/framework cần.

### 15.3. Split packages và trùng API class

Nếu hai JAR chứa cùng package hoặc cùng class, kết quả có thể khác giữa classpath và module path. Trên module path, split-package conflicts có thể làm module resolution thất bại. Trên classpath, class được nạp có thể phụ thuộc thứ tự loader/path.

Đây là lý do không nên đóng nhiều artifact “cùng API nhưng khác version” trong một runtime rồi hy vọng classloader sẽ tự chọn bản đúng.

## 16. Namespace javax.* và jakarta.*: chú ý thế hệ tiêu chuẩn

Một trong những nhóm migration quan trọng của Java enterprise là sự chuyển đổi nhiều API từ namespace `javax.*` sang `jakarta.*` trong các thế hệ Jakarta EE tương ứng.

Ví dụ:

~~~java
// Thế hệ cũ
import javax.persistence.Entity;
~~~

so với:

~~~java
// Thế hệ Jakarta mới
import jakarta.persistence.Entity;
~~~

Đây không phải chỉ là cách viết khác của cùng một class. Ở bytecode, hai tên là hai kiểu riêng biệt. API Jakarta cùng tên chức năng không tự thay thế binary reference từ API javax cũ.

### 16.1. Phải nâng cả bộ stack có liên hệ

Nếu code đã chuyển sang `jakarta.persistence.*` nhưng provider là thế hệ chỉ hiểu `javax.persistence.*`, bootstrap hoặc mapping có thể thất bại.

Nếu servlet container dùng Jakarta Servlet mới nhưng framework web cũ được compile cho `javax.servlet.*`, việc thêm cả hai API JAR thường không tạo ra một adapter thực sự.

Do đó, cần phối hợp:

1. Source imports/annotation.
2. API artifact generation.
3. Implementation generation.
4. Framework/starter version.
5. Application server/container version.
6. Dependency bắc cầu.
7. Test consumer đã biên dịch và integration workflow.

### 16.2. Đừng “sửa” bằng cách thêm cả hai namespace bừa bãi

Có hai API JAR không đồng nghĩa với bridge tương thích. Có thể tồn tại công cụ migration bytecode hoặc adapter chuyên dụng cho trường hợp cụ thể, nhưng phải xác nhận phạm vi được hỗ trợ và kiểm tra output artifact, không suy luận từ tên package.

## 17. Tương thích API/implementation có nhiều chiều

Hai artifact có vẻ đúng cặp vẫn có thể không chạy vì lệch version.

### 17.1. Source compatibility

Một implementation mới có thể yêu cầu source hoặc annotation mới. Ví dụ method mới xuất hiện trong interface API khiến code ứng dụng compile lại cần thay đổi.

### 17.2. Binary compatibility

Một implementation được biên dịch với API mới có thể gọi method không có trong API version cũ ở runtime:

~~~text
java.lang.NoSuchMethodError
~~~

Một implementation cũ có thể không cung cấp method abstract mới mà consumer/runtime mong đợi:

~~~text
java.lang.AbstractMethodError
~~~

Không nên xem hai lỗi này là bằng chứng duy nhất của mismatch; đó là những triệu chứng thường gặp, cần đối chiếu class đã nạp.

### 17.3. Semantic/behavioral compatibility

Method còn tồn tại nhưng hành vi có thể đổi:

- Validation constraint mới nghiêm ngặt hơn.
- Serializer đổi mặc định về format.
- Provider thay đổi cách transaction hoặc exception propagation.
- Logging backend đổi cách format hoặc route log.
- Driver đổi TLS defaults hoặc cách map kiểu dữ liệu.

### 17.4. Java baseline compatibility

API và implementation có thể được build cho hai JDK khác nhau. Nếu implementation yêu cầu class file major version mới hơn runtime:

~~~text
java.lang.UnsupportedClassVersionError
~~~

Việc source của ứng dụng compile với `--release 17` không tự chuyển implementation bên ngoài về Java 17.

### 17.5. Container and runtime compatibility

Một implementation có thể yêu cầu:

- Java module không nằm trong custom runtime.
- Native library và kiến trúc CPU phù hợp.
- Quyền reflection/module opens.
- File service descriptor và resource.
- Database driver/connection.
- Server lifecycle hoặc class loader behavior.

Đánh giá compatibility phải bao phủ đúng **runtime topology**, không chỉ artifact coordinates.

## 18. Chẩn đoán từ lỗi: API thiếu hay implementation thiếu?

| Triệu chứng | Khả năng cao | Kiểm tra đầu tiên |
|---|---|---|
| `package ... does not exist` lúc compile | API không ở compile classpath hoặc sai namespace | Compiler classpath, imports và dependency version |
| `cannot find symbol` | API type/method không tồn tại ở version được dùng | API artifact và source |
| `ClassNotFoundException` | Class không có ở runtime loader | Runtime classpath/module path, packaging |
| `NoClassDefFoundError` | Class từng tham chiếu không resolve/initialize được | Nested cause, classpath và initialization |
| `NoSuchMethodError` | API/implementation lệch binary hoặc dependency version conflict | Method descriptor và JAR chứa class |
| `AbstractMethodError` | Implementation không đáp ứng method runtime mong đợi | Interface/implementation version |
| `ServiceConfigurationError` | Service provider metadata hoặc type/load lỗi | `META-INF/services`, module provides |
| Provider not found | Chỉ có API hoặc provider discovery sai | Provider JAR, service descriptor và config |
| `No suitable driver` | JDBC driver không được tìm thấy/nhận URL | Driver artifact và JDBC URL |
| Không có log hoặc warning provider | SLF4J backend/provider thiếu hoặc sai generation | SLF4J API version và provider |
| `ClassCastException` giữa type “giống tên” | Hai class loader/duplicate API class | Class loader identity, WAR server libs |
| `UnsupportedClassVersionError` | Implementation cần JDK mới hơn | Class file major version |
| `InaccessibleObjectException` | Module reflection access | JDK/JPMS và framework configuration |

Một exception có thể có nhiều nguyên nhân. Ví dụ `NoClassDefFoundError` có thể do class initialization thất bại, không chỉ thiếu JAR. Phải đọc **caused by** và classloader context.

### 18.1. Dùng API class name để tìm dependency đúng

Khi gặp lỗi:

~~~text
java.lang.NoClassDefFoundError:
  jakarta/validation/Validation
~~~

đây là dấu hiệu class API có thể thiếu, không trực tiếp chứng minh provider implementation thiếu.

Nếu `Validation` class có mặt nhưng bootstrap báo không tìm provider, đó là một lớp lỗi khác.

Đọc chính xác tên class, stack trace và bước phát sinh:

- Compile: không có API.
- Class load: thiếu API hoặc phụ thuộc.
- Bootstrap: implementation/discovery/configuration.
- Invocation: version mismatch hoặc lỗi nghiệp vụ.

### 18.2. Ghi nhận JAR chứa class được nạp

Trên JDK hiện đại có thể bật class loading log trong môi trường kiểm thử:

~~~bash
java -Xlog:class+load=info -jar app.jar
~~~

Log có thể chứa nguồn mà JVM tải class. Với nested JAR, framework class loader riêng hoặc container, cần dùng cơ chế chẩn đoán tương ứng.

Trong Java, có thể kiểm tra vị trí code source của class khi classloader/security policy cho phép:

~~~java
Class<?> type = jakarta.validation.Validation.class;

var codeSource = type.getProtectionDomain().getCodeSource();

System.out.println(
        codeSource == null
                ? "No code source available"
                : codeSource.getLocation());
~~~

Không in toàn bộ đường dẫn hoặc cấu hình chứa thông tin nhạy cảm ở log public. Kiểm chứng từ classloader giúp tránh kết luận sai khi một JAR cũ vẫn tồn tại trong server runtime.

## 19. Công cụ quản lý dependency và kiểm tra artifact thực tế

### 19.1. Maven dependency tree

~~~bash
mvn dependency:tree
~~~

Để tập trung vào runtime dependency cần chọn option/scope phù hợp với phiên bản Maven plugin đang dùng. Khi điều tra, cần hiểu dependency mediation và các phiên bản bị loại vì conflict.

Một ví dụ giả định:

~~~text
app
+- example:validation-api:2.x
\- example:validator-provider:3.x
   \- example:validation-api:3.x (omitted for conflict)
~~~

Nếu runtime chọn API 2.x trong khi provider 3.x kỳ vọng API 3.x, có thể lỗi nhị phân hoặc bootstrap. Đây là dependency version mismatch, không thể “sửa” bằng một dòng import.

### 19.2. Gradle dependency graph

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

Điều tra một dependency cụ thể:

~~~bash
./gradlew dependencyInsight \
    --dependency example-validation \
    --configuration runtimeClasspath
~~~

So sánh:

- API ở compileClasspath có khác runtimeClasspath không?
- Provider nào được thêm transitively?
- Có multiple logging bindings/provider không?
- Dependency constraint hoặc platform nào quyết định version?
- Có exclude/force nào khiến implementation mất API phù hợp?
- Test runtime có khác production runtime không?

### 19.3. Nội dung JAR và service metadata

~~~bash
jar tf library.jar
~~~

Tìm:

~~~text
META-INF/services/
module-info.class
META-INF/MANIFEST.MF
~~~

Một implementation có thể cần class/service resource không hiện trong source consumer. Khi shading, minimization hoặc tạo fat JAR, phải bảo đảm service descriptor không bị mất hay ghi đè một cách sai.

### 19.4. jdeps và phân tích phụ thuộc tĩnh

~~~bash
jdeps --recursive --class-path "lib/*" app.jar
~~~

`jdeps` giúp thấy dependency ở mức bytecode và module, nhưng không chứng minh provider được phát hiện qua reflection hoặc SPI. Một implementation chỉ được nạp động có thể không xuất hiện trong static call graph.

Kết hợp jdeps với:

- Dependency graph.
- JAR content inspection.
- ServiceLoader/provider diagnostics.
- Runtime integration test.
- Class loading logs.

### 19.5. Phân tích trên đúng artifact đã phát hành

Một ứng dụng có thể chạy từ IDE vì IDE thêm API và provider vào classpath; file JAR phát hành lại không đóng chúng đúng cách. Ngược lại, WAR có thể chạy được trong container nhưng thất bại khi chạy standalone.

Vì vậy, test phải lấy đúng:

- JAR/WAR/ZIP được đóng gói.
- Runtime dependency set.
- Container/server image.
- JDK distribution và version.
- Các file service/metadata sau packaging.

## 20. Shading, fat JAR và ServiceLoader

Đóng gói các dependency trong một fat JAR có thể làm thay đổi cách provider được phát hiện.

Ví dụ hai dependency chứa file:

~~~text
META-INF/services/com.example.spi.Codec
~~~

Nếu quá trình assembly chỉ giữ một file thay vì kết hợp đúng các provider declarations, implementation còn trong JAR nhưng `ServiceLoader` chỉ thấy một provider hoặc không thấy provider nào.

Những rủi ro khác:

- Relocation đổi tên provider class nhưng service descriptor vẫn dùng tên cũ.
- Minimizer loại implementation vì chỉ được tham chiếu bằng SPI.
- Duplicate resources bị ghi đè.
- Ký JAR hoặc signature metadata không còn hợp lệ sau repackaging.
- Module descriptor không còn phù hợp với layout classpath.
- Container và fat JAR mang hai phiên bản của cùng API.

Cần dùng transformer/merge rules phù hợp với build plugin và xác nhận bằng `jar tf`, đọc service descriptors và chạy SPI discovery test từ artifact cuối cùng.

Không được kết luận dependency “đã có trong POM” thì implementation cũng đã có sau shading.

## 21. Thiết kế public library API để không rò implementation

Nếu đang phát triển một thư viện cho người khác sử dụng, việc tách API khỏi implementation giúp khả năng nâng cấp tốt hơn.

### 21.1. Tránh lộ class implementation trong method signature

Không nên thiết kế public API như:

~~~java
public VendorSpecificSession openSession();
~~~

nếu người dùng chỉ cần một hợp đồng chung. Thiết kế như:

~~~java
public Session openSession();
~~~

cho phép thay implementation mà không buộc mọi consumer import type của vendor.

Tuy nhiên, không nhất thiết luôn cần thêm interface. Mục tiêu là **không vô tình biến chi tiết nội bộ thành hợp đồng công khai**. Nếu implementation-specific type là tính năng công khai có chủ đích, cần version và quản lý compatibility tương ứng.

### 21.2. Factory và provider configuration

Một API factory tốt thường cho phép:

- Chọn implementation rõ ràng hoặc qua SPI.
- Phát hiện provider vắng mặt với thông báo lỗi hữu ích.
- Không phụ thuộc ngầm vào thứ tự classpath.
- Phân biệt “không có provider” với “provider có nhưng cấu hình sai”.
- Gắn provider với context/lifecycle phù hợp.
- Ghi nhận provider đang hoạt động để chẩn đoán.

Không nên âm thầm chọn implementation khác nếu thay đổi làm mất yêu cầu bảo mật, giao dịch hoặc dữ liệu.

### 21.3. Không dùng implementation class làm lớp truyền dữ liệu công khai

Khi expose `HibernateProxy`, class internal serializer hoặc vendor JDBC type trong API, consumer bị khóa vào implementation. Chuyển provider sau này không còn là việc thay runtime dependency đơn thuần.

Ưu tiên standard interface, DTO và contract có chủ đích cho ranh giới giữa module.

## 22. Version alignment và dependency governance

Quản lý API/provider là công việc lặp lại qua các lần nâng Java và thư viện.

### 22.1. Dùng compatibility matrix thay vì đoán theo version number

Hai artifact cùng major version chưa chắc tự động tương thích, và hai artifact khác major chưa chắc bắt buộc bất tương thích. Mỗi dự án có chính sách version riêng.

Cần đọc:

- Release notes và compatibility guide.
- JDK baseline.
- API specification generation.
- Framework/application server compatibility.
- Provider dependency requirements.
- Migration notes về namespace.
- Security fixes và end-of-support policy.

### 22.2. Phân loại vai trò trong dependency inventory

Một bảng hữu ích:

| Artifact | Vai trò | Compile? | Runtime? | Ai sở hữu version? |
|---|---|---|---|---|
| Servlet API | Contract | Có | Container cung cấp trong WAR model | Container/platform |
| Embedded server | Implementation/runtime | Tùy code | Có | Application/framework |
| Persistence API | Contract | Có | Thường cần cho provider/runtime | Framework/platform |
| ORM provider | Implementation | Tùy code | Có | Framework/BOM |
| Logging API | Facade | Có | Có | Platform/library |
| Logging backend | Provider | Không nhất thiết | Có | Application |
| JDBC driver | Database implementation | Không nếu chỉ dùng JDBC | Có | Application/platform |
| Test engine | Test implementation | Test | Test | Build/test platform |

Không nên áp một bảng chung cho mọi deployment. Ví dụ application server có thể quản lý persistence API và provider, trong khi microservice tự quản lý cả hai.

### 22.3. Dependency locking và reproducible build

Nếu ứng dụng dùng dynamic version hoặc transitive dependency không khóa, cùng một source commit có thể resolve ra provider khác tại hai thời điểm.

Có thể dùng:

- Dependency locking.
- BOM/platform thống nhất.
- Dependency constraints.
- Version catalog hoặc dependency management có review.
- SBOM cho artifact phát hành.
- Kiểm thử trên runtime dependencies đã resolve thực tế.

Locking giúp tái hiện kết quả, nhưng vẫn cần chủ động cập nhật bản vá bảo mật và kiểm chứng compatibility.

### 22.4. Tránh giải quyết một lỗi bằng cách thêm nhiều implementation

Đề xuất “thêm cả Hibernate, EclipseLink, mọi logging provider và mọi JAXB runtime để có cái chạy” gây tăng kích thước, rủi ro service ambiguity và bề mặt bảo trì.

Cách đúng:

1. Xác định hợp đồng API cần.
2. Chọn đúng provider phù hợp kiến trúc.
3. Kiểm tra phiên bản và Java baseline.
4. Loại trừ provider không mong muốn.
5. Test bootstrap và chức năng thực.
6. Ghi cách provider được chọn.

## 23. Kiểm thử tương thích API–implementation theo ma trận

Một phép thử tốt cần cả compile và runtime.

| Bài thử | API | Implementation | Kết luận cần kiểm |
|---|---|---|---|
| Compile consumer | Bản được công bố | Có thể không cần load | Public type/method hợp lệ |
| Runtime bootstrap | Bản được công bố | Provider được chọn | Provider tìm thấy và khởi tạo |
| Core operation | API đúng generation | Implementation thật | Hành vi thực thi đạt |
| Consumer cũ chạy với runtime mới | API đã compile trước | Implementation mới | Binary compatibility |
| Consumer compile lại | API mới | Provider mới | Source compatibility |
| Packaged artifact | JAR/WAR cuối cùng | Runtime/container đích | Không thiếu resource/metadata |
| JDK tối thiểu | API phù hợp | Provider bytecode phù hợp | Không vượt class file/JDK baseline |
| Negative test không có provider | API có | Không | Error rõ, không fallback sai |
| Multiple provider test | API có | Nhiều | Selection policy rõ |
| Upgrade dependency | API/provider generation mới | Bản mới | Không lệch transitive versions |

### 23.1. Một test API-only không đủ

Nếu chỉ chạy:

~~~java
assertNotNull(jakarta.validation.constraints.NotNull.class);
~~~

thì kết quả chỉ chứng minh API class được nạp. Nó không chứng minh validator hoạt động.

Cần kích hoạt operation thật:

~~~java
ValidatorFactory factory =
        jakarta.validation.Validation
                .buildDefaultValidatorFactory();

try (factory) {
    var validator = factory.getValidator();
    // Thử constraint invalid và kiểm tra violation.
}
~~~

### 23.2. Test từ consumer độc lập

Để bảo vệ thư viện public:

1. Build hoặc publish API/library artifact.
2. Tạo consumer sample độc lập.
3. Compile consumer với version được công bố.
4. Đóng gói consumer và runtime dependencies.
5. Chạy trên JDK tối thiểu được hỗ trợ.
6. Kiểm tra provider thực tế và một thao tác chức năng.
7. Thử consumer binary cũ với bản thư viện/provider mới nếu có cam kết binary compatibility.

Consumer độc lập giúp phát hiện tình huống test trong multi-module build vô tình truy cập implementation ở compile path mà người dùng thực không có.

## 24. Quy trình migration từng bước

~~~mermaid
flowchart TD
    A["Kiểm kê API, provider và runtime"] --> B["Xác định generation/version và owner"]
    B --> C["Phân loại compile/runtime/container"]
    C --> D["Nâng đồng bộ API, implementation, framework"]
    D --> E["Phân tích dependency graph và packaging"]
    E --> F["Test bootstrap trên JDK đích"]
    F --> G["Test chức năng và consumer cũ/mới"]
    G --> H{"Đạt trên artifact cuối cùng?"}
    H -->|Có| I["Phát hành kèm evidence và SBOM"]
    H -->|Không| J["Đọc lỗi, sửa classpath/provider/version"]
    J --> E
~~~

### Bước 1. Lập inventory API và implementation

Ghi mỗi cặp:

- Tên API/specification.
- Package namespace.
- API artifact coordinates và version.
- Implementation/provider coordinates và version.
- Runtime sở hữu: application, container hay server.
- Cách bootstrap: direct, factory, SPI, DI.
- JDK baseline và các module liên quan.
- Các test chứng minh provider hoạt động.
- Owner và kế hoạch nâng cấp.

### Bước 2. Tìm dependency xung đột

So sánh compile và runtime dependency graph, kiểm tra duplicate API JAR, provider không mong muốn và version bị chọn bởi mediation/BOM.

### Bước 3. Chọn stack tương thích

Chọn API, provider, framework và container cùng generation. Kiểm tra namespace `javax`/`jakarta`, class file version và chính sách Java baseline.

### Bước 4. Cấu hình scope theo deployment

Quyết định dependency nào:

- API public được export cho consumer.
- Implementation nội bộ của thư viện.
- Provider runtime-only.
- API/implementation do external container cung cấp.
- Chỉ dùng cho test.

Không copy `provided` hoặc `compileOnly` mà chưa hiểu môi trường vận hành.

### Bước 5. Xác minh service registration

Đối với SPI:

- Đúng provider JAR có mặt.
- `META-INF/services` hoặc `provides` đúng.
- Class provider nạp được.
- Resource không mất khi shading.
- Không có provider lạ được chọn ngoài ý muốn.

### Bước 6. Thử chức năng thực tế

Test HTTP request, database query, constraint validation, XML serialization, logging delivery hoặc crypto operation tương ứng. Một test chỉ lấy class hoặc in provider list không đủ.

### Bước 7. Kiểm chứng artifact và rollout

Chạy đúng artifact cuối cùng trên JDK/container/server mục tiêu; lưu checksum, dependency graph và log bootstrap. Nếu thay đổi API namespace hoặc serialization contract, cần kế hoạch nâng consumer và migration dữ liệu tương ứng.

## 25. Tình huống tổng hợp: một dự án nâng từ JDK cũ lên JDK mới

Một hệ thống cũ có:

- Web module dùng Servlet API từ container.
- Persistence module dùng JPA và ORM provider.
- XML integration dùng JAXB từng dựa vào JDK.
- Validation annotation trong DTO.
- Logging qua SLF4J.
- JDBC driver riêng theo database.

Sau khi nâng JDK và framework, nhóm gặp các lỗi:

1. JAXB class không tìm thấy.
2. Web app có xung đột giữa `javax.servlet` và `jakarta.servlet`.
3. Validation bootstrap không tìm thấy provider.
4. Logger in cảnh báo về provider.
5. JPA provider gặp lỗi method không tồn tại khi khởi tạo.
6. Driver trên production bị thiếu trong executable artifact.

Nếu xử lý theo cách “thấy thiếu class thì thêm bất kỳ JAR có tên liên quan”, classpath sẽ ngày càng khó kiểm soát.

Cách làm có cấu trúc:

| Triệu chứng | Phân loại | Hướng sửa đúng |
|---|---|---|
| JAXB class thiếu | API không còn từ JDK hoặc namespace khác | Thêm API đúng generation và runtime tương ứng |
| Servlet conflict | Container/API/framework generation mismatch | Đồng bộ cả stack và scope provided/embedded |
| Validation provider không tìm thấy | Có API, thiếu implementation/bootstrap | Chọn provider tương thích và kiểm tra SPI |
| SLF4J cảnh báo | Facade thiếu/sai backend provider | Giữ một provider đúng generation |
| JPA linkage error | API/provider/bắc cầu lệch version | Căn version qua BOM và runtime graph |
| JDBC thiếu trong packaged JAR | Runtime dependency/packaging lỗi | Đảm bảo driver vào runtime artifact |

Sau sửa, nhóm không chỉ chạy compilation mà còn khởi động artifact, gọi API, kết nối DB, validate input, serialize XML và xác nhận log được ghi, trên JDK/container đích.

## 26. Những sai lầm thường gặp

### 26.1. “Có API là đã có implementation”

Sai. Interface/annotation/factory không nhất thiết mang engine runtime. Cần một provider hoặc container có khả năng thực hiện operation.

### 26.2. “Có implementation thì không cần quan tâm API version”

Sai. Provider được biên dịch và thử nghiệm với generation API nhất định. Sai namespace hoặc lệch method descriptors có thể dẫn đến lỗi liên kết.

### 26.3. “Có import thành công thì runtime sẽ chạy”

Sai. `compileClasspath` khác `runtimeClasspath`; service metadata hoặc provider có thể bị thiếu ở artifact.

### 26.4. “Đặt provided là an toàn cho mọi ứng dụng”

Sai. `provided` chỉ hợp lý khi runtime/container thực sự cấp thành phần đó. Standalone application thường phải mang implementation hoặc dependency tương ứng.

### 26.5. “Chỉ cần thêm cả javax và jakarta JAR”

Sai. Các package names khác nhau; việc có cả hai không tạo adapter hợp lệ giữa framework và provider.

### 26.6. “BOM cung cấp toàn bộ thư viện cần thiết”

Sai. BOM quản lý version/constraints, không tự động thêm mọi implementation vào runtime.

### 26.7. “Hai provider cùng tồn tại là càng tốt”

Không nhất thiết. Có thể gây nondeterministic selection, cảnh báo, recursion qua bridge hoặc xung đột cấu hình.

### 26.8. “ServiceLoader sẽ luôn tìm ra mọi implementation”

Sai. Service descriptor, module provides, loader context và artifact packaging đều có thể làm provider không được tìm thấy.

### 26.9. “Provider được tìm thấy thì operation chắc chắn hoạt động”

Sai. Một provider có thể khởi tạo nhưng không hỗ trợ database URL, TLS config, key type, method/algorithm hoặc nghiệp vụ mong đợi.

### 26.10. “Mọi thư viện tên impl đều nên đặt runtimeOnly”

Sai. Nếu source import class cụ thể của implementation, compile cũng cần dependency. Mục tiêu kiến trúc có thể là giảm import đó, nhưng dependency declaration phải phản ánh code hiện tại.

### 26.11. “Chỉ nhìn dependency tree của test là đủ”

Sai. Test environment có thể có test-only provider, mock, embedded DB hoặc classpath rộng hơn production. Phải thử deployment artifact.

### 26.12. “Nâng JDK đồng nghĩa Java SE tự cấp API cũ”

Sai. Các module Java EE/CORBA cũ từng có trong một số JDK đã bị loại ở JDK 11; các API/implementations liên quan phải được quản lý theo runtime và version thực tế.

## 27. Checklist khi review dependency

### Hợp đồng

- [ ] Đã xác định artifact nào là API/specification và artifact nào là implementation.
- [ ] Đã biết API thuộc Java SE, Jakarta EE hay third-party specification.
- [ ] Đã ghi đúng namespace `javax.*` hoặc `jakarta.*`.
- [ ] Đã phân biệt public API dependency với implementation detail.
- [ ] Đã xác định ai chọn implementation: application, SPI, DI hay container.

### Build và version

- [ ] Đã so sánh compileClasspath và runtimeClasspath.
- [ ] Đã kiểm tra Maven scopes/Gradle configurations đúng deployment.
- [ ] Đã xác nhận BOM/platform không bị hiểu nhầm là implementation.
- [ ] Đã kiểm tra transitive dependency, conflicts, excludes và forced versions.
- [ ] Đã xác nhận API/provider cùng thế hệ và JDK baseline.
- [ ] Đã kiểm tra duplicate classes và multiple providers.

### Runtime và packaging

- [ ] Đã xác nhận provider có mặt trong runtime hoặc do server cung cấp.
- [ ] Đã kiểm tra `META-INF/services`, `module-info.class` và provider discovery.
- [ ] Đã xác minh shading/minimization không loại metadata hoặc provider.
- [ ] Đã xác nhận class được nạp từ đúng JAR và đúng class loader.
- [ ] Đã kiểm tra runtime tối thiểu và custom JRE/JDK image.
- [ ] Đã thực hiện operation thật, không chỉ kiểm tra class tồn tại.
- [ ] Đã thử consumer độc lập và artifact đã đóng gói.
- [ ] Đã lưu dependency graph, runtime version, checksum và lỗi liên quan.

### Migration

- [ ] Đã đọc compatibility guide cho API, provider, framework và container.
- [ ] Đã có kế hoạch chuyển namespace khi cần.
- [ ] Đã thử backward/binary compatibility của consumer cũ.
- [ ] Đã có rollout và rollback phù hợp với runtime topology.
- [ ] Đã gỡ provider cũ/thừa và cập nhật dependency inventory.
- [ ] Đã ghi rõ provider được chọn để dễ chẩn đoán về sau.

## Kết luận

**Bộ API** xác định hợp đồng được consumer sử dụng; **thư viện triển khai** cung cấp hành vi thực tế cho hợp đồng đó. Giữa hai lớp thường tồn tại cơ chế chọn provider như factory, `ServiceLoader`, dependency injection hoặc container. Trong Java, lựa chọn dependency phải phản ánh đúng **compile classpath, runtime classpath, version generation, module/class loader và deployment model**.

Khi nâng JDK hoặc dependency, đừng dừng lại ở việc có class và build thành công. Hãy xác định API nào đang dùng, provider nào sẽ thực thi, ai quản lý phiên bản, cách provider được phát hiện và nó có thực hiện được chức năng thật trên artifact phát hành hay không. Phân biệt đúng API và implementation giúp tránh thiếu runtime, trùng provider, lệch `javax`/`jakarta` và các lỗi compatibility khó chẩn đoán.

