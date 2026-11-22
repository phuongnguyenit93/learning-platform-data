# Phạm vi đổi namespace javax sang jakarta

Khi hiện đại hóa một ứng dụng Java EE hoặc chuyển sang framework hỗ trợ Jakarta EE, một trong những thay đổi dễ gây hiểu lầm nhất là chuyển tên package từ **javax** sang **jakarta**. Nhiều lập trình viên nghe rằng “Jakarta thay thế javax” rồi thực hiện thay thế toàn bộ chuỗi trong source. Cách làm đó có thể phá cả những API vẫn thuộc Java SE, đồng thời bỏ sót dependency, file cấu hình, service descriptor và các binary library đã được biên dịch theo namespace cũ.

Ranh giới quan trọng nhất là: **chuyển từ javax.* sang jakarta.* áp dụng cho các API thuộc những đặc tả Jakarta EE được đổi namespace từ Jakarta EE 9 trở đi; không áp dụng cho toàn bộ các package javax.* của Java.** Một ứng dụng chạy Java 21 vẫn sử dụng javax.sql.DataSource, javax.net.ssl.SSLContext hoặc javax.xml.parsers.DocumentBuilderFactory một cách bình thường.

Bài học thuộc **Java Advance Compatibility Migration**, chương **Java EE và Jakarta**. Nội dung tập trung vào phạm vi chính xác của đợt đổi namespace, ví dụ trước/sau cho các API tiêu biểu, sự liên quan của server và framework, kiểm kê các vị trí ngoài import Java, chiến lược nâng cấp đồng bộ và cách nhận diện lỗi tương thích trong quá trình chuyển đổi.

## 1. Hiểu mối quan hệ giữa Java SE, Java EE và Jakarta EE

Java Platform có những nhóm công nghệ khác nhau:

- **Java SE (Standard Edition):** ngôn ngữ, JVM và thư viện nền tảng như collections, concurrency, JDBC, XML processing, networking và cryptography.
- **Java EE (Enterprise Edition):** tập hợp các đặc tả ứng dụng doanh nghiệp như Servlet, JPA, JAX-RS, CDI, JMS, Bean Validation và các API khác.
- **Jakarta EE:** tên và hệ sinh thái phát triển tiếp những công nghệ enterprise sau giai đoạn chuyển giao Java EE sang Eclipse Foundation.

Ba tên này không đồng nghĩa với ba phiên bản ngôn ngữ Java. Đổi từ Java 8 sang Java 17 hoặc Java 21 là một công việc; đổi từ Java EE/Jakarta EE 8 sang Jakarta EE 9+ là một công việc khác. Chúng thường diễn ra cùng lúc vì framework hoặc application server mới nâng cả mức JDK tối thiểu và API enterprise.

### 1.1. Những mốc cần ghi nhớ

| Nền tảng | Namespace API enterprise chủ yếu | Ý nghĩa migration |
|---|---|---|
| Java EE 8 | javax.* | Hệ sinh thái Java EE truyền thống |
| Jakarta EE 8 | Vẫn javax.* | Đổi tên/hệ quản trị đặc tả nhưng chưa đổi toàn bộ package |
| Jakarta EE 9 | jakarta.* cho các API EE được chuyển | Bước chuyển namespace lớn |
| Jakarta EE 9.1 | jakarta.* | Tiếp tục nền tảng Jakarta EE với thay đổi baseline |
| Jakarta EE 10, 11 và các bản mới phù hợp | jakarta.* | Tiến hóa API Jakarta sau chuyển đổi |

Điểm dễ nhầm: **Jakarta EE 8 không có nghĩa source đã dùng jakarta.servlet hay jakarta.persistence.** Nhiều artifact phát hành theo thương hiệu hoặc Maven group Jakarta EE 8 vẫn chứa các class tên javax.*. Muốn xác định khả năng tương thích, phải xem **package và API level thực tế**, không chỉ tên groupId.

### 1.2. Mô hình đúng

~~~text
Java SE
  java.*
  nhiều javax.* thuộc Java SE
  (KHÔNG đổi đồng loạt)

Java EE / Jakarta EE 8
  javax.servlet.*
  javax.persistence.*
  javax.ws.rs.*
  javax.validation.*
             |
             | Jakarta EE 9 namespace migration
             v
Jakarta EE 9+
  jakarta.servlet.*
  jakarta.persistence.*
  jakarta.ws.rs.*
  jakarta.validation.*
~~~

Chuyển package không phải một phép alias. Với JVM, javax.servlet.Filter và jakarta.servlet.Filter là **hai kiểu khác tên đầy đủ**, có thể có cấu trúc tương tự nhưng không phải cùng một interface.

## 2. Phạm vi nào thực sự phải đổi?

Cách xác định đúng là xét **đặc tả sở hữu API**:

1. Package đó thuộc Java SE hay thuộc một đặc tả Java EE/Jakarta EE?
2. Artifact được dự án dùng thực sự chứa class namespace nào?
3. Target framework/container đang yêu cầu namespace nào?
4. Có dependency khác vẫn đưa kiểu javax EE vào public signature không?
5. Có file cấu hình hoặc metadata ngoài Java source dùng tên kiểu cũ không?

Với một ứng dụng chuyển từ Java EE 8/Jakarta EE 8 sang Jakarta EE 9+, phần lớn API enterprise cần chuyển import theo đặc tả tương ứng. Nhưng những API Java SE vẫn giữ nguyên.

### 2.1. Bảng mapping phổ biến

| API / lĩnh vực | Namespace cũ | Namespace Jakarta EE 9+ |
|---|---|---|
| Servlet và filter | javax.servlet.* | jakarta.servlet.* |
| Servlet HTTP | javax.servlet.http.* | jakarta.servlet.http.* |
| JSP / Jakarta Server Pages | javax.servlet.jsp.* | jakarta.servlet.jsp.* |
| Expression Language | javax.el.* | jakarta.el.* |
| Persistence / JPA | javax.persistence.* | jakarta.persistence.* |
| Bean Validation | javax.validation.* | jakarta.validation.* |
| REST / JAX-RS | javax.ws.rs.* | jakarta.ws.rs.* |
| Contexts and Dependency Injection | javax.enterprise.* | jakarta.enterprise.* |
| Dependency Injection API | javax.inject.* | jakarta.inject.* |
| Common Annotations thuộc EE | javax.annotation.* | jakarta.annotation.* |
| Enterprise Beans / EJB | javax.ejb.* | jakarta.ejb.* |
| Jakarta Transactions | javax.transaction.* | jakarta.transaction.* |
| Messaging / JMS | javax.jms.* | jakarta.jms.* |
| WebSocket | javax.websocket.* | jakarta.websocket.* |
| Faces / JSF | javax.faces.* | jakarta.faces.* |
| Security Enterprise | javax.security.enterprise.* | jakarta.security.enterprise.* |
| Interceptors | javax.interceptor.* | jakarta.interceptor.* |
| Batch | javax.batch.* | jakarta.batch.* |
| JSON Processing | javax.json.* | jakarta.json.* |
| JSON Binding | javax.json.bind.* | jakarta.json.bind.* |
| Mail | javax.mail.* | jakarta.mail.* |
| Activation | javax.activation.* | jakarta.activation.* |
| XML Binding / JAXB | javax.xml.bind.* | jakarta.xml.bind.* |
| XML Web Services / JAX-WS | javax.xml.ws.* | jakarta.xml.ws.* |
| SOAP API | javax.xml.soap.* | jakarta.xml.soap.* |
| Connectors | javax.resource.* | jakarta.resource.* |

Bảng là bản đồ định hướng theo các đặc tả đã chuyển namespace. Phải đối chiếu với **phiên bản cụ thể** của API, framework và server. Ngoài chuyển tên package, các phiên bản mới có thể có những thay đổi khác về method, hành vi, dependency hoặc cấu hình.

### 2.2. Không thay toàn bộ javax.*

Nhiều javax.* vẫn là API Java SE hoặc API độc lập không thuộc phạm vi đổi namespace nói trên:

| API vẫn giữ javax trong Java SE | Vai trò |
|---|---|
| javax.sql.DataSource | JDBC và quản lý kết nối dữ liệu |
| javax.net.ssl.SSLContext | TLS/JSSE |
| javax.crypto.Cipher | Cryptography |
| javax.naming.InitialContext | JNDI API của Java SE |
| javax.xml.parsers.DocumentBuilderFactory | XML parser |
| javax.xml.stream.XMLInputFactory | StAX |
| javax.xml.transform.Transformer | XML transformation |
| javax.xml.validation.SchemaFactory | XML schema validation |
| javax.xml.xpath.XPath | XPath |
| javax.management.MBeanServer | Java Management Extensions |
| javax.swing.JFrame | Swing GUI |
| javax.annotation.processing.Generated | Annotation processing trong Java SE |
| javax.transaction.xa.XAResource | XA/JTA integration interface nằm trong Java SE |

Đặc biệt, **javax.transaction.xa** vẫn là package Java SE, không đổi cơ học thành jakarta.transaction.xa. Tương tự, không được đổi javax.xml.parsers thành jakarta.xml.parsers: Jakarta XML Binding đổi từ javax.xml.bind sang jakarta.xml.bind, nhưng nhiều phần XML processing khác vẫn nằm trong javax.xml.* của Java SE.

### 2.3. Annotation dễ bị nhận nhầm

Hai lớp có tên ngắn tương tự nhưng xuất xứ khác nhau:

~~~java
import javax.annotation.processing.Generated;
~~~

Đây là Java SE annotation processing API, không nên đổi tùy tiện.

Trong khi đó, với Jakarta Common Annotations:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
~~~

là những annotation dùng trong vòng đời thành phần Jakarta EE hoặc framework hỗ trợ tương ứng.

Một số annotation bên ngoài như Nullable, Nonnull có thể đến từ thư viện độc lập, không phải một phần tự động được thay bằng Jakarta Common Annotations. Phải xem nguồn gốc của chính annotation đang import.

## 3. Đổi package không phải đổi tên biến

Xem một Servlet cũ:

~~~java
import javax.servlet.ServletException;
import javax.servlet.annotation.WebServlet;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

import java.io.IOException;

@WebServlet("/hello")
public class HelloServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response)
            throws ServletException, IOException {
        response.getWriter().write("Hello");
    }
}
~~~

Trong Jakarta Servlet:

~~~java
import jakarta.servlet.ServletException;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import java.io.IOException;

@WebServlet("/hello")
public class HelloServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response)
            throws ServletException, IOException {
        response.getWriter().write("Hello");
    }
}
~~~

Ở ví dụ này logic nghiệp vụ gần như không đổi. Nhưng JVM xem các superclass, annotation và parameter types mới là những class khác với namespace cũ.

### 3.1. Java source có thể sửa dễ, binary không tương thích tự động

Một method nhận:

~~~java
void register(javax.servlet.Filter filter);
~~~

không nhận đối tượng chỉ implements:

~~~java
jakarta.servlet.Filter
~~~

Hai interface khác tên đầy đủ. Nếu một thư viện cũ đã được biên dịch để nhận javax.servlet.Filter, không thể làm nó tương thích với jakarta.servlet.Filter chỉ bằng cách thêm cả hai JAR vào classpath.

Trong bytecode, reference và method descriptor chứa tên binary tương ứng. Thay namespace ảnh hưởng tới **binary linkage**, reflection, annotation scanning và framework extension points.

### 3.2. Không cố ép kiểu giữa hai namespace

Code kiểu sau không phải phương án migration:

~~~java
// Không thể giả định Servlet Filter cũ và mới tương đương:
jakarta.servlet.Filter jakartaFilter =
    (jakarta.servlet.Filter) legacyJavaxFilter;
~~~

Nếu object chỉ implements javax.servlet.Filter, việc cast không hợp lệ. Cần nâng implementation, dùng adapter ở ranh giới API được thiết kế rõ hoặc tách deployment, thay vì cưỡng ép kiểu.

## 4. Ví dụ Jakarta Persistence / JPA

Entity Java EE cũ:

~~~java
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.Table;

@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    private Long id;

    private String status;
}
~~~

Khi dùng Jakarta Persistence 3.x:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    private Long id;

    private String status;
}
~~~

**Tên table và column không tự đổi chỉ vì package annotation đổi.** Database schema có thể giữ nguyên. Tuy nhiên, runtime persistence provider phải nhận diện annotation jakarta.persistence.Entity.

### 4.1. Lỗi thường gặp khi chỉ đổi dependency

Nếu entity vẫn dùng javax.persistence.Entity nhưng Hibernate/JPA provider mục tiêu chỉ quét annotation jakarta.persistence, entity có thể không được nhận diện như entity hợp lệ.

Các triệu chứng có thể là:

- Not a managed type.
- Entity không được scan.
- Persistence unit không khởi tạo.
- Mapping exception.
- Method signature mismatch ở EntityManager/Criteria API.

Ngược lại, nếu code chuyển sang jakarta.persistence nhưng provider chỉ hỗ trợ javax.persistence, việc compile hoặc runtime integration cũng có thể thất bại.

### 4.2. Public API của DAO cũng phải thay

Một thư viện công bố method:

~~~java
javax.persistence.EntityManager getEntityManager();
~~~

đang công bố kiểu javax trên public boundary. Nếu framework mới chỉ dùng jakarta.persistence.EntityManager, mọi consumer và plugin gọi contract đó cần có chiến lược nâng cấp.

Không nên chỉ tìm import trong implementation; phải kiểm tra cả generic types, parent interfaces, method signature, annotation và metadata đã biên dịch.

## 5. Ví dụ Bean Validation và Dependency Injection

### 5.1. Bean Validation

Trước:

~~~java
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;

public final class CreateUserRequest {
    @NotBlank
    private String username;
}
~~~

Sau:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

public final class CreateUserRequest {
    @NotBlank
    private String username;
}
~~~

Mã nhìn tương tự, nhưng annotation type khác nhau. Validation provider hoặc framework binding phải hỗ trợ namespace mục tiêu. Nếu ứng dụng giữ javax.validation annotations trong một stack chỉ tích hợp Jakarta Validation, việc validation tự động có thể không chạy như kỳ vọng.

### 5.2. Dependency Injection

Trước:

~~~java
import javax.inject.Inject;
import javax.enterprise.context.ApplicationScoped;

@ApplicationScoped
public class CatalogService {
    @Inject
    CatalogRepository repository;
}
~~~

Sau:

~~~java
import jakarta.inject.Inject;
import jakarta.enterprise.context.ApplicationScoped;

@ApplicationScoped
public class CatalogService {
    @Inject
    CatalogRepository repository;
}
~~~

Đừng mặc định một CDI container theo jakarta.enterprise.* sẽ xử lý mọi javax.enterprise.* annotation cũ. Phải xem compatibility policy và version của runtime.

### 5.3. Lifecycle annotations

Trước:

~~~java
import javax.annotation.PostConstruct;
import javax.annotation.PreDestroy;
~~~

Sau:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
~~~

Nếu framework nhận diện annotation theo đúng type, giữ lại annotation namespace cũ có thể làm callback initialization/cleanup không được thực hiện. Điều đó dễ gây lỗi chỉ xuất hiện khi runtime khởi động hoặc shutdown.

## 6. Ví dụ JAX-RS / REST

Một resource cũ:

~~~java
import javax.ws.rs.GET;
import javax.ws.rs.Path;
import javax.ws.rs.Produces;
import javax.ws.rs.core.MediaType;

@Path("/ping")
public class PingResource {
    @GET
    @Produces(MediaType.TEXT_PLAIN)
    public String ping() {
        return "pong";
    }
}
~~~

Ở Jakarta REST:

~~~java
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;

@Path("/ping")
public class PingResource {
    @GET
    @Produces(MediaType.TEXT_PLAIN)
    public String ping() {
        return "pong";
    }
}
~~~

Resource còn phải được deploy trong server hoặc framework nhận annotation jakarta.ws.rs.*. Việc đổi import không tự bảo đảm route được register, JSON provider được load hoặc exception mapper hoạt động.

### 6.1. Client library cũng phải đồng bộ

Nếu một REST client thư viện cũ dùng javax.ws.rs.client.Client còn ứng dụng dùng jakarta.ws.rs.client.Client, đó là hai kiểu khác nhau. Một API provider theo namespace mới không nhận trực tiếp client type namespace cũ.

Các JAX-RS filters, exception mappers và providers cũng cần xét vì chúng implements các interface thuộc namespace cụ thể.

## 7. Những chỗ không phải Java source cũng cần migrate

Một cuộc kiểm kê chỉ tìm dòng import thường bỏ sót nhiều điểm tích hợp. Các nơi có thể chứa fully qualified class name hoặc metadata enterprise:

- web.xml và descriptor web application.
- persistence.xml, orm.xml.
- beans.xml của CDI.
- faces-config.xml và tài nguyên JSF.
- validation.xml.
- JSP directives, tag files, tag libraries và EL.
- META-INF/services của ServiceLoader.
- Tên class trong application.properties, YAML, XML hoặc database configuration.
- Reflection qua Class.forName.
- Provider registrations và plugin manifests.
- Generated source từ annotation processors.
- Bytecode dependency bên thứ ba.
- Kịch bản test, mock/proxy configuration và test utilities.
- Documentation, sample code và shared SDK cho đối tác.
- Module descriptors và deployment configuration khi có module path.

### 7.1. web.xml

Một descriptor Java EE cũ có thể khai báo namespace theo Java EE:

~~~xml
<web-app xmlns="http://xmlns.jcp.org/xml/ns/javaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://xmlns.jcp.org/xml/ns/javaee
           http://xmlns.jcp.org/xml/ns/javaee/web-app_4_0.xsd"
         version="4.0">
</web-app>
~~~

Một web.xml target Jakarta Servlet 6.0 có thể dùng namespace/schema Jakarta:

~~~xml
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           https://jakarta.ee/xml/ns/jakartaee
           https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
         version="6.0">
</web-app>
~~~

Không có quy tắc “thay chuỗi javax thành jakarta” cho tất cả XML namespaces. URI schema, tên root element, version và nội dung descriptor phải phù hợp với đặc tả/server đích. Ví dụ trên minh họa Servlet 6.0; nếu dùng Jakarta Servlet 5.0 thì cần schema/version tương ứng.

### 7.2. Persistence XML và CDI XML

Các file như persistence.xml hoặc beans.xml có version/schema riêng. Khi nâng lên một Jakarta EE release cụ thể, phải dùng định dạng descriptor mà persistence provider và CDI container đó hỗ trợ.

Không nên chỉ đổi package annotation rồi bỏ qua metadata XML. Ngược lại, không nên sửa một XML config Java SE thông thường chỉ vì nó có tiền tố javax ở thuộc tính class.

### 7.3. JSP, taglib và EL

JSP và Expression Language cũng có những API chuyển namespace. Ngoài Java imports, cần kiểm tra:

- Page directive imports.
- Custom tag handler classes.
- Tag libraries và TLD files.
- Uri của tag library theo phiên bản Jakarta Tags/JSTL.
- EL resolver, validator, converter hoặc custom expression functions.
- Các dependency JSP/Tags/EL được container cung cấp.

Một URI tag library đời cũ không được chuyển bằng một quy tắc chung cho mọi phiên bản. Cần đối chiếu documentation của Jakarta Pages/Tags và server đang triển khai.

## 8. ServiceLoader, provider và tên class dạng chuỗi

Một framework có thể tự động tìm provider qua META-INF/services.

Ví dụ resource cũ:

~~~text
META-INF/services/javax.servlet.ServletContainerInitializer
~~~

Trong stack Jakarta Servlet mới, cơ chế tương ứng có thể cần resource:

~~~text
META-INF/services/jakarta.servlet.ServletContainerInitializer
~~~

Không chỉ đổi tên file. Provider class phải triển khai đúng jakarta.servlet.ServletContainerInitializer và method descriptor tương ứng.

### 8.1. Nơi dễ bỏ sót

~~~java
Class<?> type = Class.forName(
    "javax.servlet.http.HttpServletRequest");
~~~

Đây là chuỗi, không phải import. Compiler không bắt lỗi tương thích khi chỉ sửa import ở chỗ khác.

Tương tự, file configuration có thể chứa:

~~~properties
provider.interface=javax.ws.rs.ext.ExceptionMapper
~~~

Cần xác định chuỗi này có phải tên Java class được framework load không; không thay vô tội vạ những giá trị chỉ là dữ liệu văn bản hoặc tên hợp đồng không liên quan.

### 8.2. Plugin của bên thứ ba là một biên tương thích

Plugin đã biên dịch với javax.* không tự biến thành plugin jakarta.*. Nếu framework nâng extension interface, cần:

- Bản plugin hỗ trợ Jakarta.
- Adapter hoặc gateway có chủ đích, khi thực sự khả thi.
- Release song song hai phiên bản plugin trong giai đoạn chuyển tiếp.
- Thông báo rõ API version và Java baseline cho tác giả plugin.

Một plugin có source code có thể migrate đơn giản hơn một JAR closed-source. Nhưng cả hai đều cần chạy integration tests theo namespace đích.

## 9. Dependency và tên artifact: đừng kết luận từ groupId

Sự chuyển giao sang Jakarta EE trải qua giai đoạn đổi tên artifact và sau đó đổi namespace Java. Do đó, một tọa độ Maven bắt đầu bằng jakarta không tự chứng minh các class bên trong dùng jakarta.*.

Ví dụ cần phân biệt:

~~~text
Jakarta EE 8-era artifact:
  Có thể thuộc nhóm hoặc thương hiệu Jakarta
  nhưng class vẫn dùng javax.*

Jakarta EE 9+ API artifact:
  Các API enterprise được chuyển sang jakarta.*
~~~

Cần kiểm tra **version API**, **package thực tế trong JAR** và **framework/server tương thích**.

### 9.1. Ví dụ dependency Servlet cũ

~~~xml
<dependency>
    <groupId>javax.servlet</groupId>
    <artifactId>javax.servlet-api</artifactId>
    <version>4.0.1</version>
    <scope>provided</scope>
</dependency>
~~~

Nếu deploy trên một servlet container Java EE 8, container có thể cung cấp Servlet API cho WAR. provided thể hiện rằng dependency phục vụ compile nhưng runtime thường do container cung cấp.

### 9.2. Ví dụ dependency Jakarta Servlet

~~~xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <version>6.0.0</version>
    <scope>provided</scope>
</dependency>
~~~

Ví dụ này phù hợp về ý tưởng với Jakarta Servlet 6.0. Trong thực tế, chọn API version đúng với container và Java baseline. Không nên chép số version của ví dụ nếu target server chỉ hỗ trợ Servlet 5.0 hoặc dùng phiên bản mới hơn.

### 9.3. Full Jakarta EE API trong application server

Với ứng dụng Jakarta EE đầy đủ, có thể dùng aggregate API để compile:

~~~xml
<dependency>
    <groupId>jakarta.platform</groupId>
    <artifactId>jakarta.jakartaee-api</artifactId>
    <version>10.0.0</version>
    <scope>provided</scope>
</dependency>
~~~

Ví dụ dùng Jakarta EE 10. Nếu deployment là Jakarta EE 9 hoặc một release khác, phải chọn artifact đúng mức của server. Không mang một API release cao hơn vào compile rồi deploy trên server thấp hơn mà không kiểm chứng.

**provided không thích hợp cho mọi kiểu đóng gói.** Ứng dụng executable JAR sử dụng embedded server có thể cần dependencies runtime do framework starters/BOM quản lý, không phụ thuộc vào container ngoài.

### 9.4. Gradle tương ứng

Ví dụ WAR khi container cung cấp Servlet API:

~~~groovy
dependencies {
    compileOnly "jakarta.servlet:jakarta.servlet-api:6.0.0"
}
~~~

Với Gradle WAR plugin, có thể dùng những configuration dành cho provided runtime tùy cấu trúc project. Quan trọng là không đưa một bản Servlet API sai vào gói deployment và không dựa vào compileOnly để bảo đảm container hỗ trợ đúng version.

## 10. Application server là thành phần quyết định

Khi sử dụng Servlet, JPA, CDI, Faces hoặc JMS, application server/framework thường cung cấp implementation. Mỗi generation của server hỗ trợ những đặc tả và namespace nhất định.

Ví dụ tiêu biểu:

| Nền tảng | Hướng namespace | Điều cần xác nhận |
|---|---|---|
| Apache Tomcat 9 | Servlet API javax.* | Ứng dụng Java EE Servlet thế hệ cũ |
| Apache Tomcat 10.0 | Jakarta Servlet 5.0, jakarta.* | WAR và dependency phải chuyển namespace |
| Apache Tomcat 10.1 | Jakarta Servlet 6.0, jakarta.* | Java baseline và API level phù hợp |
| Spring Framework 5.x / Spring Boot 2.x | Phần lớn integration enterprise theo javax.* | Thư viện ecosystem cũ |
| Spring Framework 6.x / Spring Boot 3.x | Jakarta EE APIs theo jakarta.* | Phải xét Java baseline và starter versions |
| Jakarta EE application servers | Theo Jakarta EE version được server công bố | Kiểm tra platform profile, API version và implementation |

Bảng chỉ trình bày hướng migration, không thay thế compatibility matrix của từng bản patch/vendor. Đặc biệt, một sản phẩm có thể hỗ trợ các API Jakarta ở mức riêng hoặc có cấu hình đặc biệt.

### 10.1. Tomcat 9 sang Tomcat 10

Một WAR dùng javax.servlet.* cho Tomcat 9 không thể được coi là tương thích tự động với Tomcat 10 chỉ vì file WAR vẫn được upload và deploy.

Cần nâng:

- Servlet imports và annotations.
- Filters, listeners và ServletContainerInitializer.
- web.xml, các descriptor liên quan.
- JSP/custom tag handlers nếu có.
- Libraries phụ thuộc javax.servlet.
- Framework sử dụng trong WAR.
- Runtime/JDK theo yêu cầu của Tomcat đích.

Tomcat có công cụ migration Jakarta EE cho một số tình huống, nhưng kết quả chuyển đổi vẫn cần kiểm thử. Không xem công cụ binary transformation là lời bảo đảm rằng mọi integration hoặc behavior đều được sửa.

### 10.2. Spring Boot 2 lên Spring Boot 3

Đây là ví dụ thường gặp của migration namespace đi cùng nâng nền tảng: Spring Framework 6/Spring Boot 3 sử dụng Jakarta API cho các điểm tích hợp EE và đòi hỏi Java baseline phù hợp (Spring Boot 3 dùng Java 17 trở lên).

Những thay đổi không chỉ gồm import:

- Spring Security config và extension points có thể đổi API.
- Hibernate/JPA provider thế hệ mới phải dùng Jakarta Persistence.
- Validation annotations và runtime phải đồng bộ.
- Embedded servlet container dùng namespace jakarta.
- Third-party starters phải tương thích với thế hệ Boot mới.
- Test framework, mock servlet request/response và các filter dùng đúng namespace.

Phải xem migration guide của đúng Spring Boot minor/major, không biến bài toán thành tìm-thay javax.* duy nhất.

## 11. Các thư viện hỗn hợp javax và jakarta có thể cùng tồn tại không?

Về mặt class loading, một JVM có thể có class javax.foo.Bar và jakarta.foo.Bar vì chúng khác tên. Nhưng **cùng tồn tại không đồng nghĩa có thể giao tiếp trực tiếp**.

Ví dụ:

~~~text
Library A:
  method filter(javax.servlet.ServletRequest)

Library B:
  object implements jakarta.servlet.ServletRequest
~~~

Library A không tự chấp nhận object của B. Nếu cố nạp cả hai API chỉ để compiler không báo thiếu class, có thể phát sinh:

- NoClassDefFoundError khi runtime thiếu package một phía.
- ClassCastException khi một object được ép kiểu sai.
- NoSuchMethodError hoặc linkage error khi descriptor không khớp.
- Annotation không được framework nhận diện.
- Provider không được ServiceLoader tìm thấy.
- Duplicate/conflicting dependency implementations.

### 11.1. Ranh giới adapter có ý nghĩa khi nào?

Nếu một thư viện legacy thực hiện một chức năng thuần dữ liệu, có thể xây adapter chuyển **dữ liệu trung lập** như DTO hoặc byte[] ở bên ngoài boundary:

~~~text
Jakarta web layer
       |
       v
Domain DTO / service interface không phụ thuộc Servlet
       |
       v
Legacy library dùng API riêng của nó
~~~

Điều này khác với adapter một-một cho toàn bộ HttpServletRequest, AsyncContext, security context hoặc transaction lifecycle. Các kiểu container này có semantics phức tạp, không thể luôn đổi namespace bằng wrapper cơ học.

Nếu subsystem chưa thể nâng, giải pháp tách thành service riêng giao tiếp qua HTTP/message/event có thể giúp giữ nguyên runtime cũ trong thời gian ngắn. Khi đó ranh giới chuyển đổi là giao thức bên ngoài, không phải giả định hai Servlet API tương đương.

## 12. JDK upgrade và Jakarta migration là hai vấn đề khác nhau

Một lỗi phổ biến: nâng Java 8 lên Java 17 rồi gặp ClassNotFoundException với javax.xml.bind.JAXBContext, sau đó kết luận mọi javax.* phải đổi sang jakarta.*.

Thực tế có hai loại thay đổi:

1. **JDK 11 loại bỏ một số module Java EE/CORBA trước đây được đóng gói cùng JDK**, như JAXB và JAX-WS, theo JEP 320. Ứng dụng có thể cần thêm dependency độc lập để tiếp tục dùng namespace cũ hoặc nâng thư viện phù hợp.
2. **Jakarta EE 9 chuyển namespace của các API EE sang jakarta.***. Đây là thay đổi source/binary contract cho hệ sinh thái enterprise.

Hai thay đổi có thể xảy ra đồng thời nhưng không phải cùng nguyên nhân.

### 12.1. Ví dụ JAXB

Ứng dụng cũ:

~~~java
import javax.xml.bind.JAXBContext;
~~~

Nếu chạy trên JDK 8, có giai đoạn API này được JDK cung cấp. Trên JDK 11+, không nên giả định module đó vẫn tồn tại trong runtime mặc định.

Nếu ứng dụng đang giữ một stack cũ tương thích javax.xml.bind, có thể dùng API/runtime JAXB cùng namespace phù hợp và được hỗ trợ trên JDK mục tiêu.

Nếu migration sang Jakarta XML Binding 3.x+:

~~~java
import jakarta.xml.bind.JAXBContext;
~~~

thì phải đồng bộ API dependency và JAXB implementation. Chỉ thêm một JAR jakarta.xml.bind vào classpath không làm bytecode javax.xml.bind của thư viện cũ tự đổi namespace.

### 12.2. Java SE vẫn có nhiều javax.* sau khi nâng JDK

Ví dụ:

~~~java
import javax.sql.DataSource;
import javax.net.ssl.SSLContext;
import javax.xml.parsers.DocumentBuilderFactory;
~~~

Các import này là những API Java SE thường dùng và không được đổi sang jakarta.*. Việc JDK hiện đại vẫn có chúng không mâu thuẫn với việc Servlet/JPA chuyển namespace.

## 13. Lộ trình kiểm kê trước khi thay namespace

Đầu tiên, liệt kê những namespace trong source và dependency. Đừng sửa code ngay chỉ dựa vào kết quả tìm kiếm.

### 13.1. Tìm import trong source

Ví dụ với ripgrep:

~~~bash
rg -n "import[[:space:]]+(static[[:space:]]+)?javax[.]" src
~~~

Sau đó phân loại từng nhóm:

- Thuộc Jakarta EE cần đổi?
- Thuộc Java SE phải giữ?
- Thuộc thư viện độc lập chưa nằm trong danh sách?
- Là generated source hay code do người viết?
- Là public API cho bên thứ ba?

Tìm những API EE phổ biến:

~~~bash
rg -n "javax[.](servlet|persistence|validation|ws[.]rs|enterprise|inject|ejb|jms|websocket|faces|el|mail|activation|xml[.]bind|xml[.]ws)" src
~~~

Lệnh này không bao phủ mọi API EE; nó là điểm bắt đầu. Với code dùng Kotlin, Scala, Groovy, JSP hoặc nguồn generated, cần mở rộng phạm vi phù hợp.

### 13.2. Tìm tên class dạng chuỗi và cấu hình

~~~bash
rg -n "javax[.]" src/main/resources src/test pom.xml
~~~

Có thể tìm trong configuration, descriptors và service registration. Nếu sử dụng modules hoặc multi-module, điều chỉnh đường dẫn tương ứng.

Không nên tự động thay mọi kết quả tìm kiếm. Ví dụ javax.net.ssl và javax.xml.parsers là Java SE; một URL tài liệu hoặc chuỗi văn bản có thể không phải tên Java type.

### 13.3. Xem dependency graph

Maven:

~~~bash
./mvnw dependency:tree
~~~

Có thể lọc theo group liên quan bằng các tùy chọn của Maven Dependency Plugin trong phiên bản dự án.

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Để truy nguyên một artifact:

~~~bash
./gradlew dependencyInsight --dependency servlet-api --configuration runtimeClasspath
~~~

Cần kiểm tra compile, runtime, test, annotation processor và các dependency được application server cung cấp. Dependency không có trong source import vẫn có thể chứa callback hoặc provider thuộc javax.*.

### 13.4. Xem class thực sự trong JAR

~~~bash
jar tf some-library.jar
~~~

Ví dụ kiểm tra xem output có:

~~~text
javax/servlet/Filter.class
~~~

hay:

~~~text
jakarta/servlet/Filter.class
~~~

Hoặc class khác tham chiếu tên javax trong bytecode dù không chứa class javax của chính nó. Công cụ như jdeps, javap hoặc bytecode/API scan có thể hỗ trợ xem dependency tĩnh và method descriptor. Reflection dùng chuỗi có thể cần tìm source/resource riêng.

## 14. Không quên test và generated source

Một dự án sau migration thường compile main source thành công nhưng test không chạy vì mock, extension hoặc fixture vẫn dùng namespace cũ.

Ví dụ:

~~~java
// Test kiểu cũ:
import javax.servlet.http.HttpServletRequest;
~~~

Trong stack Jakarta Servlet mới, test phải dùng:

~~~java
import jakarta.servlet.http.HttpServletRequest;
~~~

Điều này còn liên quan thư viện test như mock servlet API, Spring test integrations và plugin hỗ trợ chạy container. Một Mockito mock của javax.servlet.http.HttpServletRequest không thể được truyền cho method đang nhận jakarta.servlet.http.HttpServletRequest.

### 14.1. Annotation processor

Một annotation processor hoặc code generator có thể phát sinh import javax.persistence hoặc javax.annotation.Generated trong generated source.

Cần xác định:

- Generator đang nhắm Jakarta API hay Java EE API?
- Version processor hỗ trợ compiler JDK mục tiêu?
- Generated code nằm trong package nào?
- @Generated được lấy từ javax.annotation.processing hay Jakarta Common Annotations?
- Generated classes có dùng javax API trong public signatures không?

Nếu generated source bị lỗi, ưu tiên nâng generator/template hoặc cấu hình của nó. Không sửa thủ công file trong target/generated-sources rồi xem đó là migration hoàn tất.

### 14.2. Third-party library đóng gói sẵn

Một JAR chỉ phân phối binary có thể vẫn được biên dịch với javax.*. Nếu chưa có bản Jakarta-compatible, cần quyết định:

- Chờ hoặc yêu cầu vendor hỗ trợ.
- Thay library.
- Dùng công cụ bytecode transformation có đánh giá.
- Thiết kế adapter/tách subsystem ở ranh giới dữ liệu.
- Hoãn nâng module đó nhưng vẫn ghi rõ rủi ro.

Không có quy tắc an toàn rằng thêm đồng thời javax và jakarta API JAR sẽ làm thư viện cũ tương thích với server mới.

## 15. Công cụ chuyển đổi namespace có thể giúp đến đâu?

Các công cụ như **Eclipse Transformer** hoặc **Apache Tomcat Migration Tool for Jakarta EE** có thể hỗ trợ chuyển đổi một số thành phần source/binary/resource dựa trên rule phù hợp.

Tuy nhiên, migration tool không phải một trình chứng minh tương thích. Những tình huống có thể cần xử lý thủ công:

- Reflection và class name được tạo động.
- XML schema hoặc resource có semantics đặc biệt.
- Framework versions không hỗ trợ namespace mới.
- Public API thay đổi ngoài package.
- Jakarta EE API level khác mục tiêu server.
- Private/proprietary integrations.
- Annotation processor chưa nâng.
- Java agents, bytecode weaving hoặc native integrations.
- Những thư viện cùng lúc có API javax và jakarta riêng biệt.
- Serialised forms, stored class names hoặc plugin identifiers.

Một công cụ có thể làm cho class file liên kết được sau chuyển đổi mà vẫn chưa bảo đảm quy tắc transaction, lifecycle, serialization hay security giống hệ thống cũ.

### 15.1. Dùng transformer theo phạm vi có kiểm soát

Nếu bắt buộc dùng transformer:

1. Ghi rõ input artifact và checksum.
2. Xác định danh sách package/rules được chuyển.
3. Chạy trên bản sao artifact, không ghi đè binary gốc của vendor.
4. Inspect output classes/resources.
5. Chạy integration tests với target container.
6. Theo dõi issue và phiên bản tool.
7. Có đường quay lại artifact nguồn và cấu hình cũ.

Ưu tiên bản Jakarta chính thức của dependency khi đã có; transformation thường phù hợp như chiến lược chuyển tiếp có thời hạn.

## 16. Tại sao compile green chưa chứng minh migration thành công?

Một source đã đổi imports và Maven build thành công vẫn có thể gặp lỗi khi container khởi động.

Các đường runtime cần kiểm tra:

- Servlet mapping và filter chain.
- REST resource registration.
- CDI bean discovery và injection.
- @PostConstruct/@PreDestroy callbacks.
- Entity scanning và persistence unit.
- Bean Validation trên request/entity.
- JMS producer/consumer và transactional boundaries.
- WebSocket endpoint registration.
- JSP/EL/custom tags.
- Security identity và session.
- Async processing và transaction context.
- Provider discovery thông qua service descriptors.
- Deployment descriptor loading và schema validation.

Nhiều lỗi chỉ xuất hiện khi callback được gọi hoặc dữ liệu thật đi qua framework. Vì vậy, **runtime integration test** là bắt buộc cho những phần enterprise quan trọng.

### 16.1. Một số thông báo lỗi và hướng điều tra

| Triệu chứng | Khả năng thường gặp |
|---|---|
| ClassNotFoundException: javax.servlet.* | Dependency cũ cần API javax nhưng runtime chỉ có jakarta |
| NoClassDefFoundError: jakarta.persistence.* | Source/library mới cần Jakarta Persistence nhưng runtime thiếu |
| Not a managed type | Provider không nhận diện annotation/entity mapping tương ứng |
| Unsatisfied dependency | CDI/DI annotation hoặc bean discovery khác namespace |
| Servlet class is not a Servlet | Implementation thuộc interface namespace khác container |
| NoSuchMethodError | Dependency binary descriptor không khớp |
| ServiceConfigurationError | Service registration hoặc provider interface sai namespace |
| HTTP 404 sau deploy | Resource/servlet mapping không được framework register |
| Validation không chạy | Provider hoặc annotation không khớp Jakarta Validation |
| JSP compile failure | JSP/EL/taglib API/dependency chưa đồng bộ |

Bảng là hướng khoanh vùng, không phải phép chẩn đoán duy nhất. Cần xem stack trace, effective dependencies và server logs của môi trường đích.

## 17. Chiến lược migration theo lớp

Một ứng dụng lớn nên chia thành các lớp có hợp đồng rõ ràng:

~~~text
Public API / Web
  Servlet, JAX-RS, Validation
          |
          v
Application services
  Use-case / transaction boundaries
          |
          v
Domain model
  Pure Java, ít phụ thuộc EE
          |
          v
Infrastructure
  Persistence, Messaging, Mail, Security
~~~

Nếu domain layer không phụ thuộc javax.servlet, javax.persistence hoặc jakarta equivalents, công việc migration dễ cô lập hơn.

### 17.1. Bước 1 — Chốt target platform

Ghi:

- JDK runtime tối thiểu.
- Java EE/Jakarta EE API level mục tiêu.
- Application server/embedded server.
- Spring/Quarkus/Hibernate hoặc framework versions.
- Deployment model: WAR/EAR/executable JAR.
- Dependency và plugin compatibility matrix.

Đừng đổi imports trước khi biết server đích yêu cầu namespace nào.

### 17.2. Bước 2 — Kiểm kê javax theo nguồn gốc

Chia thành ba nhóm:

**Nhóm A — Jakarta EE API cần đổi:** Servlet, JPA, Validation, JAX-RS, CDI, JMS, v.v.

**Nhóm B — Java SE javax cần giữ:** SQL, SSL, crypto, JNDI, XML parsers, annotation processing, XA.

**Nhóm C — Chưa rõ:** package của thư viện độc lập hoặc annotation có nguồn gốc khác; phải đọc dependency documentation.

Mọi entry cần chỉ rõ owner và bằng chứng. Không đánh đồng nhóm B với code legacy phải loại bỏ.

### 17.3. Bước 3 — Nâng dependency/server tương thích

Ưu tiên chuyển sang các bản framework và library do nhà cung cấp công bố hỗ trợ Jakarta target. Với Maven/Gradle, dùng BOM/dependency management phù hợp để tránh kéo các phiên bản cũ qua transitive dependency.

### 17.4. Bước 4 — Sửa source và config

Đổi những package EE thực sự cần chuyển, bao gồm:

- Imports, generic signatures và annotations.
- Servlet/JPA/validation/CDI integration.
- Descriptors, provider registrations.
- JSP và resource files.
- Reflection strings và generated code.
- Test fixtures và plugin interfaces.

### 17.5. Bước 5 — Xử lý dependency legacy

Với mỗi dependency chưa chuyển:

- Có bản Jakarta-compatible không?
- Có thể thay bằng library khác không?
- Có thể cô lập thành service riêng không?
- Transformation tool có thực tế và được cho phép không?
- Nếu chưa chuyển được, có cần hoãn module hay giữ nhánh legacy không?

### 17.6. Bước 6 — Kiểm thử runtime đích

Chạy build, deployment, smoke tests, integration tests và các luồng nghiệp vụ. Khi thay persistence provider, cần test transaction và SQL mapping; khi thay servlet stack, cần test filter/security/session/async; khi thay Validation cần xác nhận constraints thực sự được kích hoạt.

### 17.7. Bước 7 — Triển khai theo giai đoạn

Ưu tiên canary hoặc staging giống production. Ghi nhận error rate, startup, 404, validation failure, persistence errors và dependency/classloader issues. Có kế hoạch rollback tương thích dữ liệu và infrastructure.

## 18. Tách Java SE upgrade khỏi Jakarta namespace upgrade khi có thể

Hai thay đổi có thể triển khai theo giai đoạn để dễ khoanh vùng:

~~~text
Giai đoạn A:
  Ứng dụng javax EE stack cũ
  Nâng build tool và JDK trong phạm vi framework hỗ trợ

Giai đoạn B:
  Nâng framework/container sang Jakarta-compatible
  Chuyển EE package javax -> jakarta
  Giữ domain/API ngoài web layer càng ổn định càng tốt

Giai đoạn C:
  Hiện đại hóa code Java, nâng thư viện và loại bỏ workaround
~~~

Không phải lúc nào cũng tách được; ví dụ target framework có Java baseline cao hơn. Khi không thể tách về deployment, ít nhất hãy tách thay đổi trong commits và kiểm thử: dependency/framework, namespace, descriptors, business refactor. Điều này giúp tìm lỗi nguồn gốc dễ hơn.

### 18.1. Tránh thay đổi wire contract không cần thiết

Đổi javax.persistence.Entity sang jakarta.persistence.Entity không yêu cầu tự động đổi:

- Tên REST endpoint.
- Tên JSON field.
- Database table hoặc column.
- Message topic.
- Contract của đối tác bên ngoài.

Nếu API JSON/DB/event còn phải ổn định, nên giữ các hợp đồng đó riêng biệt. Không trộn namespace migration với rename schema hoặc refactor nghiệp vụ nếu không cần thiết.

## 19. Cảnh báo với Java module system

Khi cùng nâng sang JDK hiện đại, dự án có thể dùng Java Platform Module System (JPMS). Đừng coi namespace migration là đồng nghĩa module name migration.

Một package Java tên jakarta.persistence không bảo đảm module descriptor của mọi implementation có tên mà bạn tự đoán. Cần xem module metadata của artifact.

Có thể kiểm tra:

~~~bash
jar --describe-module --file some-api.jar
~~~

và kiểm tra những module thực tế được resolve.

### 19.1. Reflection cũng cần được xét riêng

Framework dùng reflection vào entity/DTO có thể cần exports/opens phù hợp khi chạy trên module path.

Đổi javax.persistence thành jakarta.persistence không tự giải quyết InaccessibleObjectException. Nếu persistence provider cần private field access, module chứa entity có thể cần mở package theo cơ chế JPMS và framework version phù hợp.

### 19.2. Classpath vẫn có rủi ro

Ngay cả khi không dùng module-info.java, classpath có thể chứa cả thư viện dùng javax EE và framework Jakarta. Classloader không tự biến các type khác namespace thành tương thích.

## 20. Ví dụ checklist kiểm kê theo module

Giả sử repository gồm:

~~~text
platform/
  common-domain/
  order-api/
  order-service/
  order-web/
  batch-importer/
  partner-plugin/
~~~

Có thể đi theo bảng:

| Module | Dùng javax EE nào? | Hành động |
|---|---|---|
| common-domain | Không; chỉ Java SE | Giữ nguyên, tránh đổi imports javax SE |
| order-api | javax.validation annotations | Xác định liệu DTO public cần nâng Jakarta Validation |
| order-service | javax.transaction, javax.inject | Chuyển theo framework/platform mục tiêu |
| order-web | javax.servlet và javax.ws.rs | Chuyển Servlet/REST API và descriptors |
| batch-importer | javax.xml.bind | Nâng JAXB API/runtime nếu chuyển Jakarta XML Binding |
| partner-plugin | javax.servlet.Filter extension | Cần phiên bản Jakarta-compatible hoặc adapter strategy |

Bảng chỉ minh họa. Quan trọng là **tạo danh sách dependency và consumer cho từng module**. Những module công bố public interface javax.* có thể cần release version mới cho đối tác.

## 21. CI có thể phát hiện lẫn namespace như thế nào?

Sau khi xác định danh sách API enterprise cần đổi, có thể tạo rule tìm usage namespace cũ trong source hoặc dependency.

Ví dụ grep phạm vi Jakarta EE:

~~~bash
rg -n "javax[.](servlet|persistence|validation|ws[.]rs|enterprise|inject|ejb|jms|websocket|faces|el)" src/main
~~~

Nhưng **không** nên dùng một rule cấm tất cả javax.* vì sẽ báo sai với javax.sql, javax.crypto, javax.net.ssl, javax.xml.parsers, javax.annotation.processing hoặc javax.transaction.xa.

Với plugin kiểm tra forbidden APIs, bytecode scanning hay custom lint rule, cần cấu hình allowlist/denylist theo đặc tả. Dự án có integration legacy được cô lập có thể được đưa vào ngoại lệ có thời hạn.

### 21.1. Kiểm tra cả binary và resources

Ngoài imports:

- Inspect JAR có class references javax EE.
- Kiểm tra META-INF/services.
- Kiểm tra XML descriptors.
- Kiểm tra generated code.
- Kiểm tra shaded/relocated artifacts.
- Kiểm tra plugin được tải động và Java agents.
- Kiểm tra deployment container cung cấp API nào.

Một build xanh nhưng còn JAR javax.servlet.Filter trên đường runtime của Jakarta Servlet host cần được điều tra trước khi phát hành.

### 21.2. Chạy test tương thích đúng stack

Các bài test có ý nghĩa:

1. Servlet được register và trả đúng HTTP status.
2. Filter chain và listener được gọi.
3. JAX-RS resource mapping hoạt động.
4. CDI injection và lifecycle callbacks chạy.
5. Validation từ chối payload sai.
6. JPA provider scan entity và thực hiện transaction.
7. JMS producer/consumer gửi và nhận đúng.
8. JSP/EL/taglibs được biên dịch và render.
9. Security policy hoạt động.
10. Third-party plugins được nạp vào đúng Jakarta extension points.
11. Không còn dependency namespace cũ ở boundary quan trọng.
12. Rollback không làm dữ liệu nghiệp vụ sai.

## 22. Những hiểu lầm thường gặp

### “Mọi javax.* đều phải thành jakarta.*”

Sai. Rất nhiều javax.* thuộc Java SE vẫn phải giữ, ví dụ javax.sql, javax.net.ssl, javax.crypto, javax.xml.parsers và javax.annotation.processing.

### “Jakarta EE 8 đã đổi tên package”

Sai. Jakarta EE 8 vẫn sử dụng namespace javax trong các enterprise APIs. Đợt chuyển lớn sang jakarta diễn ra ở Jakarta EE 9.

### “Artifact có groupId jakarta nghĩa là import jakarta”

Không nhất thiết. Cần kiểm tra API version và class package thực tế, đặc biệt các artifact từ giai đoạn Jakarta EE 8.

### “Đổi imports là xong migration”

Không đúng. Còn XML descriptors, service providers, reflection strings, generated source, JSP, plugins, dependencies và server compatibility.

### “Thêm cả javax.servlet-api và jakarta.servlet-api là giải pháp”

Không đúng. Nó có thể làm compiler tìm thấy cả hai loại class, nhưng interface javax.servlet.Filter không trở thành jakarta.servlet.Filter.

### “Đổi javax.sql.DataSource thành jakarta.sql.DataSource”

Sai. javax.sql.DataSource thuộc Java SE và không chuyển theo Jakarta EE namespace migration.

### “JDK 11 mất javax.xml.bind nghĩa là javax.* phải đổi hết”

Sai. JDK 11 loại bỏ một số module Java EE khỏi JDK là một thay đổi khác với Jakarta EE 9 rename. Có thể cần thêm dependency hoặc nâng JAXB stack, tùy kiến trúc.

### “Công cụ transformer bảo đảm mọi thư viện cũ chạy trên Jakarta”

Không đúng. Binary/resource rewrite chỉ xử lý những phần phù hợp rule. Lifecycle, API behavior, classloading và framework compatibility vẫn cần integration tests.

### “Namespace mới tự yêu cầu đổi REST URL hoặc database schema”

Không đúng. Package Java và wire/schema business contract là các ranh giới khác nhau. Chỉ thay chúng nếu có lý do sản phẩm và kế hoạch compatibility riêng.

### “Compile thành công nghĩa là container sẽ nhận ra bean/entity/filter”

Không đúng. Framework có thể scan annotation/interface thuộc namespace khác. Lỗi có thể chỉ xuất hiện khi deploy hoặc khi request đầu tiên chạy.

## 23. Mẫu hồ sơ migration namespace

~~~text
PROJECT / MODULE
  Service or artifact:
  Current JDK:
  Target JDK:
  Current Java EE/Jakarta EE level:
  Target Jakarta EE level:
  Current server/framework:
  Target server/framework:
  Deployment format:

API INVENTORY
  javax EE packages requiring change:
  Java SE javax packages to preserve:
  Ambiguous third-party javax packages:
  Public APIs exposing javax types:
  Generated source:
  Reflection/class-name strings:

DEPENDENCIES
  API dependencies:
  Implementations:
  Container-provided APIs:
  Starters/BOM:
  Third-party plugins:
  Legacy libraries without Jakarta release:

RESOURCES
  web.xml:
  persistence.xml / orm.xml:
  beans.xml / faces-config.xml:
  JSP / taglib / EL:
  META-INF/services:
  App config and provider manifests:

MIGRATION DECISION
  Direct source migration:
  Supported dependency upgrade:
  Binary transformer required?:
  Adapter or process boundary:
  Exception and expiry:
  Owner:

VALIDATION
  Dependency and bytecode scan:
  Build and package:
  Server startup:
  Servlet/REST smoke test:
  Persistence/transaction test:
  Validation and DI tests:
  Messaging and plugin tests:
  Negative/security tests:
  Canary and rollback:
~~~

Hồ sơ cần ghi đủ **API level và server version**, không chỉ “đã chuyển Jakarta”. Hai ứng dụng cùng dùng jakarta.* nhưng thuộc những phiên bản Servlet/Persistence khác nhau vẫn có thể không tương thích.

## 24. Quy trình triển khai từ đầu đến cuối

### Bước 1 — Chọn đích và thu thập bằng chứng

Xác định application server/framework Jakarta-compatible, JDK tối thiểu, API level và những dependency được vendor hỗ trợ. Nếu một thư viện quan trọng còn phụ thuộc javax EE, phải nhận diện trước khi sửa source.

### Bước 2 — Phân loại javax.*

Đánh dấu:

- **MIGRATE:** các API thuộc Jakarta EE được đổi namespace.
- **KEEP:** các API Java SE hoặc API độc lập không thuộc chuyển đổi.
- **INVESTIGATE:** chưa rõ nguồn gốc hoặc chưa có bản Jakarta-compatible.

Không chạy replace-all trên toàn repository.

### Bước 3 — Nâng dependency và container

Thay API/implementation versions theo target. Loại hoặc nâng transitive dependencies dùng namespace cũ ở các boundary enterprise. Phân biệt provided API trong server với runtime dependency trong executable JAR.

### Bước 4 — Sửa source và resources

Đổi import/class references có chọn lọc; cập nhật annotations, XML descriptors, service metadata, JSP/taglib, generated code và test source.

### Bước 5 — Biên dịch và tìm điểm còn dùng javax EE

Chạy build sạch với JDK target, xem errors và dependency graph. Dùng bytecode/resource scanning để tìm class name cũ mà source grep không thấy.

### Bước 6 — Kiểm thử runtime và plugin

Deploy lên đúng server đích. Test luồng HTTP, filters, DI, JPA, Validation, JMS, Security và third-party SPI/plugin. Các bài test phải đi qua container/framework thực tế.

### Bước 7 — Canary và quan sát

Theo dõi startup, exception khi scan bean/entity, HTTP 404/500, deserialization, database transaction và plugin loading. Không chuyển toàn bộ traffic trước khi có bằng chứng runtime tốt.

### Bước 8 — Thu gọn phần tương thích tạm

Loại transformer/adapter tạm thời khi dependency chính thức đã hỗ trợ Jakarta. Gỡ các JAR namespace cũ không còn cần thiết, ngoại trừ những thành phần Java SE phải giữ.

## 25. Tổng kết

Phạm vi đổi namespace javax sang jakarta là một **thay đổi hợp đồng API enterprise** có ranh giới rõ:

1. **Jakarta EE 8 vẫn dùng javax.*; Jakarta EE 9+ chuyển phần API enterprise sang jakarta.*.**
2. **Không đổi toàn bộ javax.*** Nhiều package Java SE như javax.sql, javax.net.ssl, javax.xml.parsers và javax.transaction.xa vẫn giữ nguyên.
3. **Package đổi làm thay đổi type identity.** Interface/class javax và jakarta không tương thích nhị phân chỉ vì tên ngắn giống nhau.
4. **Dependency và container phải đồng bộ.** Source jakarta phải đi cùng framework, API provider và server tương ứng.
5. **Các vị trí ngoài import cũng quan trọng.** XML descriptors, service providers, JSP, reflection strings, generated code, plugin artifacts và test sources đều có thể cần migration.
6. **Không dùng replace-all làm chiến lược chính.** Hãy phân loại từng package theo nguồn gốc đặc tả và mức hỗ trợ.
7. **Kiểm thử runtime đầy đủ.** Compile thành công không chứng minh entity, filter, CDI bean, REST resource hay plugin được đăng ký đúng.
8. **Giữ contract nghiệp vụ tách biệt.** Không tự thay REST URL, JSON schema hoặc database chỉ vì đổi namespace Java.

Một migration thành công không phải là repository không còn chữ javax. Thành công là mọi API enterprise đã dùng đúng namespace mà platform đích hỗ trợ, các API Java SE vẫn giữ nguyên, dependency/server cùng thế hệ, và những đường xử lý thực tế hoạt động ổn định trên JDK mới.

