# Tương thích giữa thư viện javax cũ với container dùng jakarta

Khi nâng cấp ứng dụng Java EE lên Jakarta EE, một tình huống rất phổ biến là **ứng dụng hoặc thư viện cũ vẫn tham chiếu các kiểu `javax.*`**, trong khi application server, servlet container hoặc framework mới đã dùng các kiểu `jakarta.*`. Dự án có thể biên dịch thành công nhờ mang theo JAR API cũ, nhưng vẫn thất bại khi deploy, khi container quét servlet/filter/listener, khi nạp JPA entity hoặc khi khởi tạo provider cho Validation, JAX-RS và các công nghệ Java EE khác.

Nguyên nhân cốt lõi là **đổi namespace không chỉ là đổi tên import cho đẹp**. Với JVM, `javax.servlet.Filter` và `jakarta.servlet.Filter` là hai kiểu khác nhau; method descriptor, interface contract, annotation và nhiều metadata liên quan đều phải tương thích với hệ sinh thái đang chạy. Container đã chuyển sang Jakarta Servlet không có nghĩa nó tự coi một implementation `javax.servlet.Filter` là implementation `jakarta.servlet.Filter`.

Bài học này tập trung vào cách phát hiện, giải thích và xử lý ranh giới tương thích giữa **thư viện `javax` cũ** và **container dùng `jakarta`**, đặc biệt khi chuyển từ Java EE/Jakarta EE 8 sang Jakarta EE 9+, Tomcat 9 sang Tomcat 10+, hoặc Spring Framework 5/Spring Boot 2 sang Spring Framework 6/Spring Boot 3.

> Nguyên tắc chính: cần **cùng thế hệ API tại những điểm hợp đồng do container/framework quản lý**. Bổ sung cả hai API JAR vào classpath không làm hai họ type trở thành một.

## 1. Phân biệt tên Java EE, Jakarta EE và namespace

### 1.1. Java EE và Jakarta EE 8

Java EE sử dụng nhiều API thuộc namespace `javax.*`. Khi chuyển tên nền tảng thành Jakarta EE, **Jakarta EE 8 vẫn sử dụng các package `javax.*`** cho những API kế thừa từ Java EE.

Ví dụ:

```java
import javax.servlet.Servlet;
import javax.servlet.Filter;
import javax.persistence.Entity;
import javax.ws.rs.GET;
import javax.validation.NotNull;
```

Những import này không tự trở thành `jakarta.*` chỉ vì artifact hoặc tài liệu có chữ “Jakarta”.

### 1.2. Jakarta EE 9 trở đi

Jakarta EE 9 thực hiện thay đổi lớn về namespace cho các API nền tảng thuộc phạm vi Jakarta EE:

```java
import jakarta.servlet.Servlet;
import jakarta.servlet.Filter;
import jakarta.persistence.Entity;
import jakarta.ws.rs.GET;
import jakarta.validation.constraints.NotNull;
```

Một số sản phẩm hỗ trợ Jakarta EE 9.1, 10, 11 hoặc những cấp khác với các yêu cầu Java và phiên bản API riêng. **Thay đổi package bắt đầu từ Jakarta EE 9; việc chọn thế hệ container cụ thể còn phải theo API level và Java runtime của sản phẩm.**

### 1.3. Không phải mọi `javax.*` đều đổi thành `jakarta.*`

Đây là sai lầm phổ biến khi migration bằng tìm-và-thay-thế hàng loạt. Nhiều package `javax.*` thuộc **Java SE**, không phải Java EE API đổi namespace.

| Nhóm | Namespace cũ | Namespace Jakarta EE mới | Lưu ý |
|---|---|---|---|
| Servlet | `javax.servlet.*` | `jakarta.servlet.*` | Đổi ở Jakarta Servlet 5.0 |
| Persistence/JPA | `javax.persistence.*` | `jakarta.persistence.*` | Jakarta Persistence 3.0 |
| JAX-RS | `javax.ws.rs.*` | `jakarta.ws.rs.*` | Jakarta RESTful Web Services 3.0 |
| Bean Validation | `javax.validation.*` | `jakarta.validation.*` | Jakarta Validation 3.0 |
| CDI | `javax.enterprise.*`, `javax.inject.*` | `jakarta.enterprise.*`, `jakarta.inject.*` | Phải xem cả DI implementation |
| JMS | `javax.jms.*` | `jakarta.jms.*` | Messaging client/provider phải cùng thế hệ |
| JAX-WS | `javax.xml.ws.*` | `jakarta.xml.ws.*` | SOAP stack cũng cần tương ứng |
| JAXB | `javax.xml.bind.*` | `jakarta.xml.bind.*` | Chú ý JAXB không còn bundled trong JDK 11 |
| Jakarta Annotations | Phần Java EE `javax.annotation.*` | `jakarta.annotation.*` | Không đổi nhầm `javax.annotation.processing.*` |
| Java SE JDBC | `javax.sql.*` | **Vẫn `javax.sql.*`** | Không tìm `jakarta.sql` |
| Java SE XML | `javax.xml.parsers.*`, `javax.xml.transform.*` | **Vẫn `javax.xml.*`** | Không đổi các API XML Java SE |
| Java SE crypto | `javax.crypto.*`, `javax.net.ssl.*` | **Vẫn `javax.*`** | Không thuộc thay đổi Jakarta EE |
| JTA/XA thuộc Java SE | `javax.transaction.xa.*` | **Vẫn `javax.transaction.xa.*`** | Khác API Jakarta Transactions `jakarta.transaction.*` |

Một thư viện `javax.crypto` hoặc `javax.sql` có thể chạy bình thường trong container Jakarta vì nó dùng API Java SE. Do đó, phải xác định **đúng package và đúng spec**, không chỉ tìm chuỗi `javax`.

## 2. Source compatibility, binary compatibility và runtime contract

### 2.1. JVM coi `javax.servlet.Filter` và `jakarta.servlet.Filter` là hai type

Phiên bản cũ:

```java
package com.example.web;

import javax.servlet.Filter;

public final class AuditFilter implements Filter {
    // Triển khai phương thức theo javax Servlet API.
}
```

Phiên bản mới:

```java
package com.example.web;

import jakarta.servlet.Filter;

public final class AuditFilter implements Filter {
    // Triển khai phương thức theo jakarta Servlet API.
}
```

Dù tên class của ứng dụng vẫn là `com.example.web.AuditFilter`, danh sách interface trong bytecode đã khác. Một object triển khai `javax.servlet.Filter` **không tự động là** `jakarta.servlet.Filter`.

Ví dụ bằng logic kiểu:

```java
// Container Jakarta mong chờ kiểu này:
jakarta.servlet.Filter filter = ...;
```

Một instance của class cũ chỉ implements `javax.servlet.Filter` không thể được gán hợp lệ vào biến trên chỉ vì hai API có method tương tự.

### 2.2. Thay đổi method descriptor

Giả sử thư viện định nghĩa extension point:

```java
// API cũ
void initialize(javax.servlet.ServletContext context);
```

Sau khi chuyển:

```java
// API mới
void initialize(jakarta.servlet.ServletContext context);
```

Ở mức JVM, descriptor khác nhau:

```text
Cũ: (Ljavax/servlet/ServletContext;)V
Mới: (Ljakarta/servlet/ServletContext;)V
```

**Đổi package làm thay đổi binary type identity và descriptor**, dù tên method, kiểu logic và nội dung source gần giống nhau.

Khi một binary đã biên dịch tìm method có descriptor cũ nhưng runtime chỉ cung cấp descriptor mới, có thể gặp `NoSuchMethodError`. Nếu runtime không tìm được class `javax/servlet/...`, có thể gặp `NoClassDefFoundError`. Loại lỗi cụ thể còn tùy đường class loading và thao tác thực hiện.

### 2.3. Compile thành công không đảm bảo deploy thành công

Một module có thể khai báo cả hai API:

```text
javax.servlet-api.jar
jakarta.servlet-api.jar
```

Vì chúng có FQCN khác nhau, compiler có thể chấp nhận cả hai họ type trong cùng source tree. Nhưng điều đó **không làm container Jakarta thực hiện `javax.servlet.Filter` như một Jakarta Filter**.

Đây là ví dụ source compilation success nhưng runtime integration failure.

### 2.4. Container integration là hợp đồng cần tuân thủ

Container không chỉ nạp `.class`. Nó có thể:

- Tìm implementation của `jakarta.servlet.Servlet`, `Filter` và listener interfaces.
- Quét annotation như `jakarta.servlet.annotation.WebServlet`.
- Nạp `jakarta.persistence.Entity` cho JPA provider.
- Tìm CDI annotations, REST resources và Validation constraints.
- Quản lý dependency injection, session, transaction, security và lifecycle hooks.

Thư viện cũ khai báo annotation hoặc interface thuộc họ `javax` thường không tham gia đúng hợp đồng này trong container Jakarta thuần túy.

## 3. Tình huống Servlet: Tomcat 9 so với Tomcat 10+

Một ví dụ dễ quan sát là hệ sinh thái Tomcat.

| Runtime container | Thế hệ Servlet API tiêu biểu | Namespace |
|---|---|---|
| Tomcat 9 | Servlet 4.0 | `javax.servlet.*` |
| Tomcat 10.0 | Jakarta Servlet 5.0 | `jakarta.servlet.*` |
| Tomcat 10.1 | Jakarta Servlet 6.0 | `jakarta.servlet.*` |
| Tomcat 11 | Jakarta Servlet 6.1 | `jakarta.servlet.*` |

**Tomcat 10+ không phải bản nâng cấp thả vào thay thế hoàn toàn cho ứng dụng Servlet `javax` cũ.** Cần chuyển namespace và kiểm tra các thay đổi spec/container liên quan.

Một số sản phẩm như Jetty có thể cung cấp nhiều deployment environment cho các mức EE khác nhau trong cùng dòng sản phẩm. Đó là tính năng riêng phải cấu hình và xác nhận; không suy rằng mọi “container Jakarta” đều hỗ trợ `javax` trực tiếp.

### 3.1. Servlet cũ

```java
package com.example.web;

import java.io.IOException;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

public final class HealthServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response)
            throws ServletException, IOException {
        response.setContentType("text/plain");
        response.getWriter().write("OK");
    }
}
```

Đoạn code này thuộc hợp đồng `javax.servlet.http.HttpServlet`. Nếu deploy trực tiếp lên runtime chỉ nhận Jakarta Servlet API, container không thể tự biến class đó thành `jakarta.servlet.http.HttpServlet`.

### 3.2. Servlet chuyển sang Jakarta

```java
package com.example.web;

import java.io.IOException;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

public final class HealthServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response)
            throws ServletException, IOException {
        response.setContentType("text/plain");
        response.getWriter().write("OK");
    }
}
```

Phần logic hầu như không đổi, nhưng type contract với container đã thay đổi thật sự.

Nếu class của ứng dụng còn extends `javax.servlet.http.HttpServlet` trong artifact, chỉnh `web.xml` hoặc thêm `jakarta.servlet-api.jar` một mình chưa đủ.

### 3.3. Filter cũng phải theo namespace của container

Với Jakarta Servlet:

```java
package com.example.web;

import java.io.IOException;
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;

public final class AuditFilter implements Filter {
    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {
        // Ghi audit trước hoặc sau khi gọi chuỗi filter.
        chain.doFilter(request, response);
    }
}
```

Nếu một thư viện bảo mật cũ chỉ cung cấp filter kiểu `javax.servlet.Filter`, container Jakarta không thể coi nó là filter theo API mới. Cần bản thư viện Jakarta tương thích, chuyển đổi binary đã được kiểm chứng hoặc viết adapter có chủ đích.

## 4. Dependency `provided`/`compileOnly`: đúng vai trò nhưng không sửa namespace

Trong WAR truyền thống, Servlet API thường do container cung cấp. Vì vậy khi biên dịch ứng dụng Jakarta Servlet, dependency API thường là `provided` trong Maven hoặc `compileOnly` trong Gradle.

### 4.1. Maven cho Jakarta Servlet

```xml
<dependencies>
    <dependency>
        <groupId>jakarta.servlet</groupId>
        <artifactId>jakarta.servlet-api</artifactId>
        <version>6.0.0</version>
        <scope>provided</scope>
    </dependency>
</dependencies>
```

Version ví dụ phải phù hợp với mức Jakarta Servlet do container đích hỗ trợ. Không copy version 6.0.0 sang Tomcat 10.0 vốn thuộc thế hệ Servlet 5.0 rồi giả định tương thích đầy đủ.

### 4.2. Gradle Groovy DSL

```groovy
plugins {
    id 'war'
}

dependencies {
    compileOnly 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}
```

Khi dùng WAR plugin, cần xem đúng configuration, packaging task và cách container cung cấp API. Với Spring Boot executable JAR dùng embedded server, cơ chế dependency runtime khác WAR triển khai lên application server.

### 4.3. Tại sao không nhét `javax.servlet-api` vào WAR mới?

Một hướng sửa sai thường gặp:

```text
WEB-INF/lib/javax.servlet-api.jar
WEB-INF/lib/jakarta.servlet-api.jar
```

Việc bổ sung API JAR cũ có thể khiến class `javax.servlet.*` được tìm thấy, nhưng nó không tạo implementation runtime Javax Servlet tương ứng bên trong một container Jakarta. Nó cũng không biến `javax.servlet.Filter` thành `jakarta.servlet.Filter`, hay khiến container quét annotation Javax như annotation Jakarta.

Đây là sự khác nhau giữa:

1. **Class có tồn tại để nạp?**
2. **Class có đúng interface/annotation mà container yêu cầu?**
3. **Container có cung cấp implementation và lifecycle tương ứng?**

Giải quyết câu 1 không tự giải quyết câu 2 và 3.

### 4.4. Tránh trộn container API với app dependency một cách tùy tiện

Đưa nhiều bản `jakarta.servlet-api` hoặc JAR implementation của servlet container vào `WEB-INF/lib` có thể tạo xung đột classloader hoặc version. Hãy để container sở hữu API/provider theo hợp đồng của nó, trừ khi packaging mode (ví dụ embedded server) có quy tắc riêng.

## 5. Thư viện `javax` thuần Java vẫn có thể dùng được khi nào?

Không phải mọi thư viện cũ có chữ `javax` đều không tương thích.

### 5.1. Thư viện dùng API Java SE ổn định

Ví dụ thư viện dùng:

```java
import javax.sql.DataSource;
import javax.crypto.Cipher;
import javax.net.ssl.SSLContext;
import javax.xml.parsers.DocumentBuilderFactory;
```

Những package này thuộc Java SE và không đổi thành Jakarta chỉ vì application server lên Jakarta EE. Dù thư viện cũ, nó có thể tiếp tục chạy nếu bytecode, JDK API, provider và các dependency khác tương thích.

### 5.2. Thư viện không đi qua container contract

Một thư viện xử lý thuần Java như cấu trúc dữ liệu, thuật toán hoặc kết nối HTTP độc lập có thể chạy trong container Jakarta dù được viết từ thời Java EE, miễn không mang theo yêu cầu runtime vào các API EE `javax.*`.

Trường hợp thư viện chứa API Javax ở một nhánh chức năng không sử dụng, có thể chạy được nhưng vẫn có rủi ro nạp class qua reflection, static initializer, service provider hoặc đường chạy hiếm. Cần kiểm tra dependency và integration thực tế.

### 5.3. Thư viện ở boundary được tách khỏi ứng dụng

Một service Java EE cũ chạy độc lập có thể giao tiếp với ứng dụng Jakarta mới qua HTTP/JSON, SOAP contract hoặc message protocol tương thích. Khi không trao đổi trực tiếp Java object implement `javax.servlet.*`/`jakarta.servlet.*`, ranh giới wire protocol có thể giúp hệ thống nâng cấp từng phần.

Tuy nhiên, các hợp đồng JSON, XML, WSDL, message schema, authentication và transaction boundaries vẫn cần được quản lý rõ ràng.

## 6. Không phải cứ thấy artifact `jakarta.*` là namespace đã chuyển

Một điểm dễ gây nhầm lẫn trong dependency management: **tọa độ artifact và Java package không phải một**.

Ở giai đoạn Jakarta EE 8, có những artifact nhóm `jakarta.*` nhưng **class vẫn khai báo `javax.*`**. Ví dụ, dòng Jakarta Servlet 4.0 và Jakarta Persistence 2.2 vẫn gắn với thế hệ `javax`.

| API thế hệ trước | Giai đoạn dùng `javax` | Giai đoạn chuyển `jakarta` |
|---|---|---|
| Servlet | Java EE 8 / Jakarta Servlet 4.0 | Jakarta Servlet 5.0+ |
| Persistence | JPA/Jakarta Persistence 2.2 | Jakarta Persistence 3.0+ |
| REST/JAX-RS | JAX-RS/Jakarta REST 2.1 | Jakarta REST 3.0+ |
| Bean Validation | Jakarta Bean Validation 2.0 | Jakarta Validation 3.0+ |
| CDI | CDI/Jakarta CDI 2.0 | Jakarta CDI 3.0+ |

Vì vậy, **đừng xác định namespace bằng `groupId` hoặc `artifactId`**. Cần xem phiên bản spec và class file thực tế trong JAR.

Kiểm tra nhanh:

```bash
jar tf jakarta.servlet-api-6.0.0.jar
```

Tìm đường dẫn:

```text
jakarta/servlet/Filter.class
```

Với artifact cũ:

```text
javax/servlet/Filter.class
```

Chỉ sau khi xác minh class path trong JAR mới kết luận artifact thuộc namespace nào.

## 7. Những lỗi runtime thường gặp

### 7.1. `NoClassDefFoundError` cho kiểu Javax

Ví dụ:

```text
java.lang.NoClassDefFoundError:
  javax/servlet/Filter
```

Có thể xảy ra khi ứng dụng hoặc dependency vẫn tham chiếu Javax Servlet trong khi runtime chỉ cung cấp Jakarta Servlet. Cần tìm **artifact nào chứa reference đó**, chứ không chỉ thêm Javax API JAR cho hết lỗi.

Nếu bổ sung JAR Javax mà runtime không có implementation đúng hợp đồng, lỗi có thể chuyển thành lỗi khác lúc container instantiate hoặc register filter.

### 7.2. `ClassCastException`

Ví dụ logic:

```text
Cannot cast com.example.LegacyFilter
to jakarta.servlet.Filter
```

Nếu class cũ chỉ implements `javax.servlet.Filter`, phép cast sang Jakarta interface thất bại. Lỗi này phản ánh type identity khác nhau, không phải vì phương thức `doFilter` thiếu tên giống nhau.

### 7.3. `NoSuchMethodError`

Một phương thức nhận `javax.servlet.ServletContext` khác với phương thức nhận `jakarta.servlet.ServletContext`, như đã thấy ở method descriptor. Một library compile theo Javax API nhưng runtime chỉ có library Jakarta thay thế có thể gặp lỗi linkage.

### 7.4. `AbstractMethodError`

Có thể xuất hiện khi runtime chọn method/interface contract mà implementation đã biên dịch không cung cấp theo đúng descriptor và kiểu. Đây là một dạng binary incompatibility cần phân tích cùng class file và dependency graph, không phải lỗi source compilation đơn thuần.

### 7.5. `ClassNotFoundException` trong reflection

Framework có thể tra tên class qua chuỗi:

```java
Class.forName("javax.persistence.Entity");
```

Nếu API Javax không tồn tại, lookup thất bại. Dùng tool chuyển binary chỉ thay class references nhưng không thay mọi chuỗi cấu hình/reflection có thể khiến lỗi này còn sót.

### 7.6. CDI/annotation không được nhận diện

Một class có `javax.inject.Inject` hoặc `javax.enterprise.context.ApplicationScoped` có thể bị container Jakarta không xem là annotation tương ứng nếu không có cơ chế tương thích cụ thể.

Kết quả có thể là injection không xảy ra, bean không được tạo hoặc application fail deployment. Cần nâng toàn bộ DI integration/provider theo phiên bản container.

### 7.7. Lỗi provider hoặc `ServiceLoader`

Một dependency có metadata:

```text
META-INF/services/javax.some.Service
```

trong khi API mới tìm provider dưới:

```text
META-INF/services/jakarta.some.Service
```

Có thể không tìm thấy provider, hoặc provider class không implement đúng interface mới. Việc thay `.class` chưa chắc đủ nếu service descriptor và metadata chưa được chuyển đổi.

Các tên trên chỉ minh họa cấu trúc path; tên service thực tế phụ thuộc spec/provider.

## 8. JPA/Hibernate: annotation entity và provider phải cùng thế hệ

JPA là ví dụ điển hình cho việc code có thể biên dịch nhưng không được provider nhận diện.

### 8.1. Entity Javax

```java
import javax.persistence.Entity;
import javax.persistence.Id;

@Entity
public class Customer {
    @Id
    private Long id;
}
```

### 8.2. Entity Jakarta

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class Customer {
    @Id
    private Long id;
}
```

Một provider Jakarta Persistence mong đợi annotation Jakarta. Nếu entity còn annotation Javax, provider có thể không xem class là managed entity và báo lỗi mapping/runtime.

### 8.3. Không chỉ đổi annotation

Migration JPA thường còn bao gồm:

- `EntityManager`, `EntityManagerFactory`, `Persistence`, `TypedQuery` và interface trong API.
- `persistence.xml`, schema URI/namespace, version và provider class.
- Các property có prefix `javax.persistence.*` chuyển theo Jakarta spec khi tương ứng.
- Hibernate/JPA provider, transaction integration và bytecode enhancer.
- Các entity listeners, converters, validation integration và CDI injection.
- Criteria API, metamodel generator, annotation processors.
- Database driver/JDBC: `javax.sql.*` vẫn là Java SE API, không đổi theo Jakarta namespace.

Nếu dùng Hibernate, cần chọn đúng phiên bản/biến thể hỗ trợ Jakarta Persistence, không kết luận máy móc rằng mọi Hibernate 5 chỉ hỗ trợ Javax hay mọi Hibernate 6 cấu hình giống nhau. Phải căn cứ artifact cụ thể và ma trận hỗ trợ của framework.

### 8.4. Đừng đóng gói hai JPA provider tùy tiện

Thêm cả JPA API Javax/Jakarta và hai provider có thể dẫn đến xung đột classpath, persistence unit discovery hoặc transaction integration. Một Jakarta container đã cung cấp một số dịch vụ; ứng dụng cần theo mô hình quản lý provider của container hoặc framework, không tự nhúng thêm tất cả bản API lẫn implementation.

## 9. REST/JAX-RS: resource và provider cần API cùng namespace

REST endpoint cũ:

```java
import javax.ws.rs.GET;
import javax.ws.rs.Path;
import javax.ws.rs.Produces;

@Path("/health")
public class HealthResource {
    @GET
    @Produces("text/plain")
    public String status() {
        return "OK";
    }
}
```

Jakarta REST:

```java
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;

@Path("/health")
public class HealthResource {
    @GET
    @Produces("text/plain")
    public String status() {
        return "OK";
    }
}
```

Không chỉ controller/resource cần chuyển. Các provider như `ContainerRequestFilter`, `MessageBodyReader`, `ExceptionMapper`, `Application` và runtime implementation của JAX-RS cũng thuộc contract mới.

Một JAX-RS provider JAR cũ chỉ implement `javax.ws.rs.ext.MessageBodyReader` không tự động trở thành provider `jakarta.ws.rs.ext.MessageBodyReader`, dù logic chuyển đổi JSON giống nhau.

Nếu API client và server giao tiếp qua HTTP/JSON, client Javax và server Jakarta **có thể** tương tác ở wire protocol nếu endpoint, authentication, media type và payload contract tương thích. Nhưng nếu chúng chia sẻ một binary Java extension interface trực tiếp, cần đồng bộ type namespace.

## 10. Bean Validation: constraint annotation và validator

Một thư viện model cũ có:

```java
import javax.validation.constraints.NotNull;

public class OrderInput {
    @NotNull
    private String customerId;
}
```

Model chuyển sang Jakarta:

```java
import jakarta.validation.constraints.NotNull;

public class OrderInput {
    @NotNull
    private String customerId;
}
```

Validator engine Jakarta sẽ tìm annotation, `ConstraintValidator` và provider theo hợp đồng Jakarta Validation. Chỉ giữ annotation Javax trong DTO có thể khiến validation bị bỏ qua hoặc gây lỗi integration tùy framework.

Cần xem cả:

- Custom constraint annotation.
- `ConstraintValidator` implementations.
- `Validation.buildDefaultValidatorFactory()` và bootstrap provider.
- Hibernate Validator hoặc implementation khác ở phiên bản Jakarta.
- CDI integration và JPA validation hooks.
- Method validation trên controller/service.
- Message bundle và XML validation mapping.

**Bỏ sót validation có thể gây lỗi nghiệp vụ âm thầm**, khác với lỗi startup ngay lập tức. Đây là lý do migration cần cả kiểm thử âm tính (dữ liệu không hợp lệ phải bị từ chối).

## 11. Spring Framework và Spring Boot: cùng thay đổi namespace, nhưng phạm vi rộng hơn

Một số cột mốc đại diện:

| Hệ sinh thái | Mức phổ biến | Servlet/EE integration |
|---|---|---|
| Spring Framework 5.x | Thế hệ trước | Chủ yếu dùng `javax` cho Servlet và tích hợp EE tương ứng |
| Spring Framework 6.x | Thế hệ mới | Chuyển sang Jakarta EE APIs |
| Spring Boot 2.x | Dùng Spring Framework 5 | Chủ yếu nằm trong hệ sinh thái `javax` |
| Spring Boot 3.x | Dùng Spring Framework 6 | Yêu cầu hệ sinh thái Jakarta |

Một ứng dụng Spring Boot 2 không thể chỉ đổi container từ Tomcat 9 sang Tomcat 10 rồi kỳ vọng toàn bộ servlet filters và framework integrations tự tương thích.

Tương tự, nâng lên Spring Boot 3 có thể cần thay:

- Import Servlet API trong controller/filter/listener.
- JPA/Validation annotations và providers.
- Servlet container/embedded server version.
- Security framework/filter chain tương ứng.
- OpenAPI/documentation libraries dùng annotations Javax.
- Monitoring, tracing, serialization, servlet adapters và framework starters.
- Custom `HandlerInterceptor` hoặc integration cấp servlet khi có type signature liên quan.

Không nên tùy ý ghim Spring Framework core hoặc Servlet API version riêng ngoài BOM/starter của Spring Boot nếu chưa hiểu ma trận hỗ trợ. BOM của framework thường giúp điều phối các dependency theo một thế hệ API.

## 12. Jakarta Transactions và trường hợp Java SE `javax.transaction.xa`

Sự chuyển đổi này có một bẫy:

- Nhiều API Jakarta Transactions chuyển từ `javax.transaction.*` sang `jakarta.transaction.*`.
- Nhưng `javax.transaction.xa.*` là một phần Java SE và **không chuyển thành `jakarta.transaction.xa.*`** theo cùng quy tắc.

Nếu công cụ migration thay mọi chuỗi `javax.transaction` thành `jakarta.transaction` mà không phân biệt package, source có thể sai ngay ở phần XA interfaces.

Điều này còn ảnh hưởng transaction manager, JTA integration, JDBC resource và container-managed transactions. Khi nâng framework, phải kiểm tra cả driver, XA provider và transaction coordinator.

## 13. JAXB, JAX-WS, XML và SOAP

Một số thư viện Java EE cũ dùng JAXB/JAX-WS:

```java
import javax.xml.bind.JAXBContext;
import javax.xml.ws.Service;
```

Thế hệ Jakarta tương ứng:

```java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.ws.Service;
```

Tuy nhiên, **`javax.xml.parsers.DocumentBuilderFactory` và `javax.xml.transform.TransformerFactory` vẫn thuộc Java SE**. Không được thay đại trà `javax.xml.*` thành `jakarta.xml.*`.

### 13.1. Nâng JDK và đổi Jakarta là hai vấn đề khác nhau

JAXB và JAX-WS từng được cung cấp cùng JDK trong các phiên bản cũ nhưng bị loại khỏi JDK từ Java 11. Một ứng dụng Java 8 sang Java 11 có thể gặp lỗi thiếu class JAXB/JAX-WS **ngay cả khi vẫn chạy container Javax**.

Giải pháp có thể là bổ sung đúng các dependency tương ứng với thế hệ Javax hoặc Jakarta mà ứng dụng đang dùng. Không nên đồng nhất “API bị tách khỏi JDK” với “API đã đổi namespace”.

### 13.2. XML/WSDL tương thích theo hợp đồng wire

Một SOAP service triển khai bằng stack Javax và client triển khai bằng stack Jakarta có thể giao tiếp nếu WSDL, XML schema, binding, WS-* policy và security tương thích. Nhưng generated Java stubs, provider internals và JAXB annotations ở mỗi phía cần thuộc đúng stack tương ứng.

Nên tái generate client/server code từ WSDL bằng bộ công cụ phù hợp với runtime, thay vì copy generated class Javax vào một ứng dụng Jakarta mà không kiểm tra.

## 14. Cách kiểm tra JAR cũ còn phụ thuộc `javax` hay không

### 14.1. Liệt kê class bằng `jar`

```bash
jar tf legacy-library.jar
```

Tìm dấu hiệu class Javax nếu artifact là một API JAR:

```bash
jar tf legacy-library.jar | grep '^javax/'
```

Nhưng đây chỉ tìm **class được đóng gói bên trong JAR**. Một library có thể tham chiếu `javax.servlet.Filter` mà không chứa class Javax nào trong chính artifact đó.

### 14.2. Dùng `jdeps` để quan sát dependency bytecode

Ví dụ:

```bash
jdeps --recursive \
  --class-path "lib/*" \
  legacy-library.jar
```

Kết quả có thể cho biết class/package nào được thư viện tham chiếu. Với dependency bị thiếu, cần bổ sung classpath phân tích tương ứng để xác định tham chiếu.

Giới hạn: `jdeps` phân tích tham chiếu tĩnh, **không thể chứng minh không có** string-based reflection, ServiceLoader, XML descriptor hoặc class được tạo động.

### 14.3. Dùng `javap` để xem descriptor

Ví dụ với class extension:

```bash
javap -classpath legacy-library.jar \
  -s com.example.integration.LegacyExtension
```

Nếu thấy:

```text
(Ljavax/servlet/ServletContext;)V
```

thì binary contract vẫn tham chiếu Javax Servlet, bất kể artifact filename hoặc Maven group.

Một bản Jakarta đúng sẽ dùng type tương ứng:

```text
(Ljakarta/servlet/ServletContext;)V
```

### 14.4. Xem metadata không nằm trong class descriptor

Các dấu vết còn sót có thể nằm trong:

- `META-INF/services/...` và service provider configuration.
- `web.xml`, `web-fragment.xml`, taglib descriptors.
- `persistence.xml`, `beans.xml`, `validation.xml`.
- JSP taglibs/JSTL imports và expression-language integration.
- XML mapping/ORM descriptors hoặc serializer configuration.
- String literal trong code dùng `Class.forName("javax...")`.
- Annotation processors, generated sources và codegen templates.
- OSGi bundle manifest, Automatic-Module-Name hoặc framework plugin metadata.

Vì vậy, đổi import và build pass mới là một phần của quá trình chuyển đổi.

## 15. Maven: kiểm tra hai họ dependency

Một Maven project có thể đồng thời kéo Javax và Jakarta versions qua các nhánh transitive.

Xem dependency graph:

```bash
mvn dependency:tree
```

Thu hẹp tìm kiếm theo artifact khi cần:

```bash
mvn dependency:tree -Dincludes=javax.servlet:javax.servlet-api
mvn dependency:tree -Dincludes=jakarta.servlet:jakarta.servlet-api
```

Tùy nền tảng, còn cần tìm `javax.persistence`, `jakarta.persistence`, `javax.validation`, `jakarta.validation`, JAX-RS/REST và runtime implementations tương ứng.

### 15.1. Hai API JAR không nhất thiết trùng class

Javax và Jakarta Servlet API nằm dưới hai package khác nhau, nên đây không nhất thiết là duplicate FQCN theo nghĩa classpath truyền thống. Tuy nhiên, **nó là dấu hiệu trộn thế hệ API ở boundary**.

Hai phiên bản Jakarta Servlet API khác nhau cùng cung cấp `jakarta.servlet.Filter` lại có thể là duplicate FQCN hoặc version collision. Phải phân loại vấn đề cụ thể.

### 15.2. Khi nào dùng exclusions?

Ví dụ nếu một SDK cũ kéo `javax.servlet-api` vào WAR Jakarta trong khi không cần dependency đó ở runtime, có thể cân nhắc exclude đúng nhánh. Nhưng exclusion không biến code trong SDK từ Javax thành Jakarta.

Nếu SDK còn compile reference đến `javax.servlet.Filter`, loại API JAR có thể làm lỗi lộ ra nhanh hơn, qua đó giúp xác định dependency cần thay hoặc nâng.

Đừng exclude bừa toàn bộ các dependency tên `javax.*`; một số là Java SE hoặc vẫn cần cho phần hệ thống chưa migration.

### 15.3. BOM/framework-managed versions

Với hệ thống Spring Boot 3 hoặc Jakarta EE platform, nên dựa vào BOM hoặc danh mục dependency được khuyến nghị của framework/container khi có thể. Việc override riêng một provider sang thế hệ Javax có thể phá vỡ integration giữa JPA, Validation, CDI hoặc Servlet dù API JAR là Jakarta.

Cần đồng bộ API level, provider implementation, container và Java runtime.

## 16. Gradle: kiểm tra `compileClasspath` và `runtimeClasspath`

Gradle có thể resolve khác nhau cho compilation và runtime.

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
```

Tập trung vào một API:

```bash
./gradlew dependencyInsight \
  --dependency jakarta.servlet-api \
  --configuration runtimeClasspath
```

Trong WAR deploy vào container, Servlet API thường chỉ cần ở compile classpath:

```groovy
dependencies {
    compileOnly 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}
```

Nếu dùng Spring Boot embedded container, hãy theo dependency model của Boot starter; không áp dụng máy móc `compileOnly` vì servlet implementation cần có ở runtime của ứng dụng độc lập.

### 16.1. Bản dependency được chọn chưa chắc là bản được deploy

Một WAR có thể được copy thêm JAR bằng custom packaging task. Một Docker image có thể chứa application server đã tích hợp API khác version, hoặc mang theo thư viện legacy trong thư mục chung.

Vì thế, kiểm tra **cả resolved graph và nội dung WAR/JAR/runtime image cuối cùng**. Build tool không quản lý toàn bộ classloader của application server trừ khi quy trình deploy được thiết kế rõ.

### 16.2. Compiler target không giải quyết namespace

`sourceCompatibility`, `targetCompatibility` hoặc `options.release` chỉ liên quan mức Java source/bytecode/API Java SE. Chúng không biến `javax.servlet.Filter` thành `jakarta.servlet.Filter`.

Bạn có thể compile thư viện Javax bằng JDK 17 mà nó vẫn là thư viện Javax. Cũng có thể chạy một container hỗ trợ Javax trên JDK mới; **JDK version và Jakarta API generation là hai trục lựa chọn độc lập**.

## 17. Ba chiến lược migration chính

### 17.1. Chiến lược A: nâng thư viện lên bản Jakarta chính thức

**Ưu tiên hàng đầu** nếu nhà phát hành có bản hỗ trợ Jakarta.

Quy trình:

1. Xác định class nào của SDK/library tham chiếu Javax EE APIs.
2. Tìm phiên bản/biến thể Jakarta chính thức.
3. Xem yêu cầu JDK, framework/container và API level của thư viện mới.
4. Nâng các dependencies đi kèm (JPA provider, validation engine, REST implementation, servlet integration).
5. Cập nhật import/descriptor/annotation trong ứng dụng.
6. Build và deploy bằng container Jakarta đích.
7. Chạy integration test trên endpoint, transactions, validation và lifecycle thực tế.

Ưu điểm: được vendor duy trì, ít phụ thuộc bytecode transformation, giảm công việc tự quản. Nhưng nâng major version có thể kéo theo thay đổi API/semantics khác ngoài namespace, cần đọc migration guide và test.

### 17.2. Chiến lược B: chuyển source và tái biên dịch

Nếu bạn sở hữu source của thư viện:

1. Chọn Jakarta API level/container mục tiêu.
2. Đổi có kiểm soát các import Java EE liên quan từ `javax.*` sang `jakarta.*`.
3. Giữ nguyên các `javax.*` thuộc Java SE.
4. Cập nhật dependency API và implementation.
5. Cập nhật XML descriptors, annotations, provider metadata, reflection strings.
6. Recompile, chạy test và phát hành artifact phiên bản mới.

Ví dụ:

```diff
-import javax.servlet.Filter;
-import javax.servlet.ServletRequest;
-import javax.servlet.ServletResponse;
+import jakarta.servlet.Filter;
+import jakarta.servlet.ServletRequest;
+import jakarta.servlet.ServletResponse;
```

Cùng lúc, cần sửa chữ ký phương thức dùng những kiểu này trong API public.

Đây thường là giải pháp bền vững hơn cho thư viện nội bộ, vì source có thể được review, sửa semantically và bảo trì.

### 17.3. Chiến lược C: bytecode/namespace transformation như cầu nối

Khi chưa có source hoặc nhà phát hành chưa cung cấp bản Jakarta, có thể đánh giá công cụ chuyển đổi artifact như:

- **Apache Tomcat Jakarta EE Migration Tool**: hỗ trợ chuyển một số ứng dụng Java EE 8 từ Javax namespace sang Jakarta cho các môi trường phù hợp.
- **Eclipse Transformer**: chuyển đổi namespace và metadata theo các rule/phiên bản công cụ được cấu hình.

Công cụ transformer có thể sửa class references và một số resources/metadata, nhưng cần xác minh **phạm vi chuyển đổi cụ thể**. Không phải mọi framework extension, native component, reflection dynamic string hoặc file serialization đều có thể biến đổi hoàn toàn.

Không nên gọi bytecode transformer một lần rồi kết luận binary đã tương thích: phải kiểm tra kết quả và chạy đầy đủ integration tests.

## 18. Những giới hạn của bytecode transformation

### 18.1. Reflection và tên class dạng chuỗi

Ví dụ:

```java
Class<?> type = Class.forName("javax.servlet.http.HttpServlet");
```

Nếu transformer không đổi string liên quan, runtime vẫn yêu cầu class Javax. Một số transformer có rule xử lý strings/resources, nhưng khả năng cụ thể phải được xác minh theo cấu hình và bản công cụ.

### 18.2. Dữ liệu serialized và contract bên ngoài

Nếu hệ thống lưu dữ liệu dùng tên class Javax hoặc generated proxy trong serialized payload, thay binary namespace có thể làm quá trình đọc dữ liệu cũ thất bại.

Không áp dụng transformer lên định dạng dữ liệu production mà chưa thiết kế versioning và migration dữ liệu.

### 18.3. SPI/service descriptors

Một provider có thể khai báo service file theo tên interface Javax. Nếu chỉ đổi class bytecode mà không đổi `META-INF/services`, `ServiceLoader` vẫn không phát hiện provider như mong đợi.

### 18.4. Annotation và XML descriptors

Framework có thể đọc annotations, XML namespaces, deployment descriptors hoặc generated proxies. Cần xác minh package/namespace trong:

```text
WEB-INF/web.xml
META-INF/persistence.xml
META-INF/beans.xml
META-INF/services/*
WEB-INF/*.tld
```

Không sửa XML namespace URI một cách máy móc nếu không biết specification/schema của container.

### 18.5. Chữ ký JAR và bảo mật chuỗi cung ứng

Biến đổi bytecode/resources làm thay đổi nội dung JAR và có thể vô hiệu hóa chữ ký số hiện có. Artifact mới cần có provenance, checksum, signing và quy trình xác minh mới.

Không đem JAR đã biến đổi từ nguồn không kiểm chứng vào production chỉ vì nó khởi chạy được.

### 18.6. Các dependency còn lại vẫn thuộc Javax

Transformer áp dụng cho một JAR không tự chuyển các JAR khác. Nếu library A được chuyển sang Jakarta nhưng library B vẫn nhận `javax.servlet.ServletRequest` ở public API, lời gọi giữa A và B vẫn không khớp.

Hãy xử lý **toàn bộ dependency graph của vùng ứng dụng liên quan** hoặc đặt boundary adapter rõ ràng.

## 19. Vì sao adapter không thể chỉ là cast?

Một sai lầm là cố ép kiểu:

```java
// Không có quan hệ subtype trực tiếp giữa hai interface:
jakarta.servlet.Filter f =
        (jakarta.servlet.Filter) legacyJavaxFilter;
```

Cast không tạo quan hệ implement mới. Nếu object chỉ implements Javax interface, phép cast có thể thất bại với `ClassCastException`.

### 19.1. Adapter đúng là implementation riêng

Về nguyên tắc, adapter phải **implements giao diện Jakarta** và dùng API/đối tượng Jakarta thực sự ở phía container:

```java
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import java.io.IOException;

public final class ModernFilterAdapter implements Filter {
    private final LegacyAuditLogic delegate;

    public ModernFilterAdapter(LegacyAuditLogic delegate) {
        this.delegate = delegate;
    }

    @Override
    public void doFilter(
            ServletRequest req,
            ServletResponse res,
            FilterChain chain)
            throws IOException, ServletException {
        delegate.recordRequest(req.getRemoteAddr());
        chain.doFilter(req, res);
    }
}
```

Ở đây, `LegacyAuditLogic` là **business logic độc lập với Servlet APIs** do ứng dụng sở hữu; adapter chuyển những dữ liệu cần thiết sang mô hình không phụ thuộc `javax` hoặc `jakarta`. Đây là cách tiếp cận phù hợp khi có quyền sửa kiến trúc.

### 19.2. Bridge đầy đủ giữa Servlet API cũ và mới rất phức tạp

Nếu thư viện legacy yêu cầu nguyên object `javax.servlet.ServletRequest`, việc dựng adapter từ `jakarta.servlet.ServletRequest` không chỉ là viết một method. Nó kéo theo nhiều interface/method, session/context semantics, async processing, lifecycle, request/response wrappers, listener và có thể thay đổi API spec.

Vì vậy, **đừng tự viết cầu nối Servlet API toàn phần nếu chỉ cần một chức năng nghiệp vụ**. Tốt hơn là nâng SDK, chuyển source hoặc tách logic khỏi Servlet boundary.

### 19.3. Boundary qua HTTP hoặc message là lựa chọn khác

Nếu không thể chuyển một thư viện Javax ngay, có thể tạm giữ nó trong **một service/container riêng hỗ trợ Javax**, rồi giao tiếp với ứng dụng Jakarta qua HTTP hoặc message schema trung lập.

Cách này hỗ trợ migration từng phần, nhưng bổ sung chi phí deploy, latency, security, observability và compatibility của wire protocol. Không xem nó là giải pháp miễn phí.

## 20. Tách classloader có giải quyết được không?

Classloader isolation có thể cho phép hai thư viện với các dependency riêng cùng tồn tại trong một process, nhưng **không tự thay đổi Javax type thành Jakarta type**.

Ví dụ:

```text
Parent/container classloader:
  jakarta.servlet.*

Plugin classloader:
  javax.servlet.*
  legacy-plugin.jar
```

Plugin có thể nạp các class Javax riêng, nhưng muốn container gọi nó như `jakarta.servlet.Filter` vẫn cần một adapter thực thi hợp đồng Jakarta.

Việc dùng cùng tên package ở hai classloader cũng tạo nguy cơ class identity/cast conflicts. Với container có khả năng chạy song song nhiều môi trường EE khác nhau, phải theo **deployment environment và classloading contract chính thức** của sản phẩm.

Không thay thứ tự classpath hoặc bật parent-last classloading chỉ để “ép” container Jakarta dùng Javax Filter; đây là vấn đề type contract, không đơn thuần search order.

## 21. Những lựa chọn thực tế khi thư viện chưa có bản Jakarta

| Tình huống | Hướng ưu tiên | Giới hạn cần lưu ý |
|---|---|---|
| SDK có bản Jakarta chính thức | Nâng version/biến thể được vendor hỗ trợ | Có thể có breaking changes khác namespace |
| Thư viện nội bộ có source | Chuyển source, đổi API/import/metadata, biên dịch lại | Cần test contract và integration |
| Thư viện nhỏ chỉ có business logic | Tách logic Java SE khỏi servlet/JPA boundary, viết adapter mới | Cần thay entrypoint và lifecycle |
| JAR bên thứ ba không có source | Thử transformer có rule được kiểm soát | Reflection, resources, serialization và signing có thể vỡ |
| Sản phẩm legacy không thể nâng ngay | Giữ ở container Javax riêng, giao tiếp qua HTTP/message | Tăng vận hành và quản lý API giữa services |
| Container hỗ trợ nhiều EE environments | Dùng môi trường deployment đúng thế hệ | Phụ thuộc sản phẩm/cấu hình cụ thể; không mặc định |
| App còn ở Javax và chưa có yêu cầu Jakarta | Tạm giữ container Javax được hỗ trợ về security | Cần đánh giá vòng đời hỗ trợ và rủi ro vận hành |

Việc chọn hướng chuyển phải dựa trên hỗ trợ chính thức của thư viện/container và yêu cầu security, không chỉ theo khả năng compile.

## 22. Quy trình điều tra trong WAR/JAR thực tế

### Bước 1 — Ghi rõ 4 phiên bản

Xác định:

1. JDK/runtime version.
2. Servlet/Jakarta EE API generation.
3. Container/server version.
4. Framework và các thư viện tích hợp chính.

**Không gộp thành một câu “chúng ta dùng Java 17”.** Java 17 có thể chạy ứng dụng Javax trên container Javax, hoặc ứng dụng Jakarta trên container Jakarta, tùy ma trận hỗ trợ.

### Bước 2 — Nhận diện contract bị lỗi

Dựa vào exception:

```text
javax/servlet/Filter
jakarta/servlet/Filter
javax/persistence/Entity
jakarta/persistence/Entity
```

Xem class nào đang yêu cầu type Javax, class nào do container Jakarta cung cấp.

### Bước 3 — Khảo sát dependency graph

Maven:

```bash
mvn dependency:tree
```

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Tìm cả API JAR và implementation/provider; đừng chỉ tìm một chuỗi package.

### Bước 4 — Kiểm tra artifact deploy

Ví dụ WAR:

```bash
jar tf build/libs/app.war
```

Quan sát:

```text
WEB-INF/classes/
WEB-INF/lib/
WEB-INF/web.xml
```

Xem API JAR cũ có bị đóng gói vào WAR không. Xem SDK nào còn reference Javax EE. Nếu dùng Spring Boot executable JAR, kiểm tra nested dependency JAR và embedded container version thay vì áp dụng quy tắc WAR một cách cứng nhắc.

### Bước 5 — Phân tích binary references

Dùng `jdeps` và `javap` với classpath phù hợp, tìm descriptors chứa `Ljavax/...` hoặc `Ljakarta/...`.

### Bước 6 — Chọn cách migration

Ưu tiên vendor Jakarta release, sau đó source migration, adapter hoặc transformer có kiểm soát; nếu không thể thì tách thành dịch vụ legacy riêng.

### Bước 7 — Test từng extension point

Không chỉ load một trang HTML. Cần thử:

- Servlet/filter/listener lifecycle.
- REST endpoints và exception mapper.
- JPA entity scanning, CRUD, transactions.
- Validation với input không hợp lệ.
- CDI dependency injection.
- Authentication/authorization/session.
- Messaging/JMS và SOAP nếu dùng.
- Reflection, service providers và generated code.

### Bước 8 — Đưa artifact vào container đích

Chạy smoke/integration test trên cùng container version, runtime image, classloader và packaging mode như production.

### Bước 9 — Cố định dependency và ghi nhận bằng chứng

Lưu BOM/platform, dependency tree, artifact checksum, vendor/runtime versions và kết quả test. Điều này giúp phát hiện regression khi một dependency transitive quay trở lại Javax.

## 23. Ví dụ tổng hợp: WAR Javax lên Tomcat 10.1

Giả sử ứng dụng Java EE cũ đang chạy Tomcat 9:

```text
inventory.war
  WEB-INF/classes/com/example/web/InventoryServlet.class
  WEB-INF/lib/legacy-auth-filter.jar
```

Trong đó:

- `InventoryServlet` extends `javax.servlet.http.HttpServlet`.
- `legacy-auth-filter.jar` implements `javax.servlet.Filter`.
- Một số validation annotations sử dụng `javax.validation.*`.

Khi chuyển nguyên WAR sang Tomcat 10.1:

1. Container cung cấp Jakarta Servlet 6.0.
2. Servlet/Filter cũ vẫn tham chiếu Javax types.
3. Thêm `jakarta.servlet-api.jar` vào WAR không làm chúng trở thành Jakarta types.
4. Deploy có thể lỗi class loading/type contract, hoặc ứng dụng không đăng ký filter như mong đợi.
5. Validation có thể không được thực thi nếu chỉ một phần stack đã chuyển.

**Phương án ưu tiên:**

1. Nâng `legacy-auth-filter` lên bản dành cho Jakarta Servlet nếu có.
2. Chuyển source Servlet và các listener/filters nội bộ sang `jakarta.servlet.*`.
3. Chuyển Validation annotations và provider sang Jakarta tương ứng.
4. Cập nhật `web.xml`, taglibs/JSP metadata và các resource liên quan.
5. Chọn Servlet API version theo Tomcat 10.1, để container cung cấp.
6. Build WAR mới và xem các JAR trong `WEB-INF/lib`.
7. Triển khai trên Tomcat 10.1 và test endpoint/authorization/validation/session.

Nếu `legacy-auth-filter` không có bản Jakarta và không thể chuyển, cân nhắc adapter nghiệp vụ hoặc công cụ transformation có test; nếu không đáp ứng, giữ riêng phần Javax ở một runtime tương thích trong giai đoạn chuyển tiếp.

## 24. Lỗi hiểu nhầm thường gặp

### “Jakarta EE 8 đã chuyển hết sang `jakarta.*`”

**Sai.** Jakarta EE 8 vẫn sử dụng namespace Javax cho những API nền tảng tương ứng. Chuyển đổi lớn sang Jakarta namespace xuất hiện ở Jakarta EE 9.

### “Chỉ đổi `javax` thành `jakarta` ở import là xong”

**Không đủ.** Cần xem dependencies, providers, XML/metadata, annotation processors, resource files, reflection, compiled JARs và API signatures.

### “Thêm hai API JAR là làm ứng dụng tương thích cả hai”

**Sai với container contracts.** Hai họ type độc lập; container Jakarta cần implementation của Jakarta interfaces.

### “Tên Maven group `jakarta.*` đảm bảo bên trong là `jakarta.*`”

**Không chính xác.** Artifact ở thời Jakarta EE 8 có thể có tọa độ Jakarta nhưng class vẫn nằm dưới `javax.*`.

### “Nâng JDK 17 sẽ tự đổi ứng dụng Javax sang Jakarta”

**Sai.** JDK version và EE namespace là hai trục độc lập; `--release` cũng không làm thay đổi package của dependency.

### “Toàn bộ `javax.*` đều phải đổi”

**Sai.** Nhiều API Java SE như `javax.sql`, `javax.crypto` và `javax.xml.parsers` vẫn giữ nguyên.

### “Bytecode transformer luôn xử lý hết”

**Sai.** Reflection strings, metadata, JSP/TLD, service files, serialization, provider compatibility và chữ ký JAR có thể cần xử lý bổ sung.

### “Tách classloader là cast được Javax Filter sang Jakarta Filter”

**Sai.** Classloader isolation không tạo quan hệ subtype giữa hai interface khác tên.

### “Tomcat 10 và Tomcat 9 chỉ khác số phiên bản”

**Sai.** Tomcat 10 thuộc thế hệ Jakarta Servlet với thay đổi namespace, chưa kể những thay đổi spec/Java version khác.

## 25. Checklist trước khi xác nhận tương thích

- [ ] Đã phân biệt Jakarta EE 8 (`javax`) và Jakarta EE 9+ (`jakarta`).
- [ ] Đã xác định runtime JDK, container, Servlet API level và framework version.
- [ ] Đã kiểm kê thư viện nào còn reference Javax EE API.
- [ ] Đã giữ nguyên các package `javax` thuộc Java SE.
- [ ] Đã kiểm tra JAR thực tế, không dựa vào Maven group name.
- [ ] Đã kiểm tra bytecode descriptor bằng `javap` hoặc phân tích tương đương.
- [ ] Đã xem Maven/Gradle dependency graph ở đúng runtime configuration.
- [ ] Đã loại API JAR không phù hợp khỏi WAR khi container cung cấp API tương ứng.
- [ ] Đã chuyển Servlet/filter/listener và các extension points khác sang thế hệ API mới.
- [ ] Đã cập nhật JPA entities, persistence provider và configuration khi có liên quan.
- [ ] Đã cập nhật REST resources/providers và Validation annotations/engine.
- [ ] Đã kiểm tra CDI/JMS/SOAP/JAXB/Jakarta Transactions nếu ứng dụng dùng chúng.
- [ ] Đã kiểm tra metadata, service files, XML descriptors và reflection strings.
- [ ] Đã xác nhận các transformer/adapter nếu có bằng integration tests.
- [ ] Đã kiểm thử WAR/JAR thực sự được deploy trên container mục tiêu.
- [ ] Đã có lộ trình riêng cho thư viện Javax chưa có bản Jakarta.
- [ ] Đã lưu dependency graph, container version, artifact và kết quả regression test.

## 26. Kết luận

Tương thích giữa thư viện Javax cũ và container Jakarta không thể đánh giá chỉ bằng việc mã nguồn có compile được hay không. Từ Jakarta EE 9, những API thuộc phạm vi đổi namespace mang **type identity mới**: `javax.servlet.Filter` không phải `jakarta.servlet.Filter`, annotation Javax không tự tương đương annotation Jakarta, và JVM method descriptors thay đổi theo package. Một container Jakarta không tự cung cấp bridge cho mọi thư viện Javax cũ.

Cách migration bền vững là **kiểm kê đúng API theo thế hệ, giữ các `javax.*` thuộc Java SE, nâng library/provider lên bản Jakarta được hỗ trợ, chuyển source và metadata, rồi kiểm thử artifact thật trên container đích**. Với thư viện không thể nâng ngay, adapter nghiệp vụ, transformer được kiểm chứng hoặc runtime legacy tách riêng là các phương án chuyển tiếp cần kiểm soát. Đích cuối cùng không chỉ là tránh `ClassNotFoundException`, mà là toàn bộ servlet, persistence, validation, injection và integration lifecycle hoạt động đúng trong một hệ sinh thái API nhất quán.
