
# Phân biệt Java SE, Java EE và Jakarta EE trong bài toán chuyển đổi

Một dự án Java lâu năm có thể gặp các lỗi tưởng như mâu thuẫn khi nâng JDK: `java.sql.Connection` vẫn tồn tại, `javax.servlet.http.HttpServlet` không tìm thấy nếu chỉ có JDK, `javax.xml.bind.JAXBContext` từng chạy trên Java 8 nhưng biến mất khi dùng Java 11, còn bản framework mới lại yêu cầu `jakarta.persistence.Entity` thay cho `javax.persistence.Entity`. Nếu quy tất cả vào việc “Java đổi tên thư viện” hoặc “JDK bỏ Java EE”, người thực hiện migration rất dễ thêm sai dependency, trộn hai thế hệ API, hoặc triển khai lên application server không tương thích.

Điểm cốt lõi là **Java SE, Java EE và Jakarta EE là những tập nền tảng/đặc tả khác nhau**, có lịch sử và ranh giới cung cấp API, implementation, runtime khác nhau. Việc nâng **JDK** không tự động nâng **Jakarta EE**, và việc thay đổi namespace `javax.*` sang `jakarta.*` không áp dụng cho toàn bộ Java SE.

Bài học nằm trong *Java Advance Compatibility Migration*, chủ đề *Java EE và Jakarta*. Nội dung trình bày cách phân loại các API, nhận diện phần do JDK hoặc application server cung cấp, hiểu quá trình chuyển từ Java EE sang Jakarta EE, đánh giá mã nguồn–binary–runtime compatibility, và xây dựng kế hoạch nâng cấp có thể kiểm chứng.

## 1. Ba tên gọi mô tả những tầng nào?

### 1.1. Java SE — nền tảng Java tiêu chuẩn

**Java Platform, Standard Edition (Java SE)** định nghĩa các API cốt lõi và môi trường thực thi Java chuẩn. Các ví dụ phổ biến:

- Ngôn ngữ Java, compiler `javac` và cách biên dịch qua JDK.
- `java.lang`, `java.util`, `java.io`, `java.nio`.
- Collection, concurrency, networking và `java.time`.
- JDBC API thuộc `java.sql`, `javax.sql`.
- Java Cryptography Architecture, `javax.crypto` và các API bảo mật tiêu chuẩn.
- XML parsing/processing API như `javax.xml.parsers`, `javax.xml.transform`, `org.w3c.dom` trong các module Java SE tương ứng.
- Các API liên quan `javax.annotation.processing` dùng cho annotation processing.

Java SE thường được sử dụng cùng JDK hoặc runtime image chứa module cần thiết. Nhưng một **custom runtime image** tạo bằng `jlink` có thể chỉ mang các module đã chọn, nên không thể mặc định mọi image đều chứa tất cả module có trong JDK đầy đủ.

Một API có tên bắt đầu bằng `javax.` **không tự động là Java EE API**. Ví dụ `javax.crypto.Cipher` là API Java SE; chuyển import thành `jakarta.crypto.Cipher` là sai.

### 1.2. Java EE — thế hệ nền tảng enterprise trước Jakarta

**Java Platform, Enterprise Edition (Java EE)** là nền tảng/nhóm đặc tả cho ứng dụng enterprise. Nhiều API Java EE dùng package `javax.*`, ví dụ:

- `javax.servlet.*`: HTTP servlet.
- `javax.persistence.*`: Java Persistence API (JPA).
- `javax.validation.*`: Bean Validation.
- `javax.ws.rs.*`: JAX-RS cho REST.
- `javax.enterprise.inject.*`: CDI.
- `javax.ejb.*`: Enterprise JavaBeans.
- `javax.jms.*`: Java Message Service.
- `javax.transaction.*`: Java Transaction API.
- `javax.mail.*`: Mail API trong những thế hệ tương ứng.
- `javax.xml.bind.*` và `javax.xml.ws.*`: JAXB/JAX-WS trong hệ sinh thái Java EE.

Các API enterprise có thể được **application server** cung cấp hoặc do ứng dụng khai báo từ thư viện bên ngoài. Chúng không đồng nghĩa với “mọi API Java EE đều là thành phần bắt buộc của JDK”.

### 1.3. Jakarta EE — sự tiếp nối của nền tảng enterprise

**Jakarta EE** là thế hệ tiếp nối sau khi việc phát triển Java EE được chuyển sang Eclipse Foundation. Các đặc tả enterprise tiếp tục được phát triển, nhưng có một điểm chuyển quan trọng về namespace:

- **Java EE 8**: chủ yếu dùng API `javax.*`.
- **Jakarta EE 8**: vẫn giữ các package `javax.*` cho nhiều đặc tả, dù tên nền tảng đã thay đổi.
- **Jakarta EE 9 trở đi**: nhiều package enterprise được đổi sang `jakarta.*`.

Ví dụ:

~~~java
// Java EE / Jakarta EE 8 generation
import javax.persistence.Entity;
import javax.servlet.http.HttpServlet;

// Jakarta EE 9+ generation
import jakarta.persistence.Entity;
import jakarta.servlet.http.HttpServlet;
~~~

Sự thay đổi là **tên đầy đủ của kiểu Java**, không chỉ là chỉnh một nhãn hiển thị. `javax.persistence.Entity` và `jakarta.persistence.Entity` là hai annotation type khác nhau, và bytecode đã biên dịch tham chiếu đến hai tên khác nhau.

## 2. Bảng so sánh ngắn về phạm vi và trách nhiệm

| Thuộc tính | Java SE | Java EE | Jakarta EE |
|---|---|---|---|
| Mục đích | API lõi, ngôn ngữ, runtime Java chuẩn | Enterprise/web APIs của thế hệ trước | Enterprise/web APIs được phát triển tiếp |
| Ví dụ API | `java.util`, `java.time`, `java.sql` | `javax.servlet`, `javax.persistence` | `jakarta.servlet`, `jakarta.persistence` |
| Thường được cung cấp bởi | JDK/runtime modules | Application server hoặc dependency | Jakarta-compatible server hoặc dependency |
| Có bắt buộc đi cùng JDK không? | Thành phần nền tảng, tùy module/image | Không; một số API phụ trợ từng được bundle trong JDK lịch sử | Không |
| Namespace | `java.*` và một số `javax.*` thuộc SE | Nhiều `javax.*` | Nhiều `jakarta.*` từ EE 9 |
| Ví dụ triển khai | JDK vendor/runtime image | Java EE application server | Jakarta EE application server, provider/embedded runtime phù hợp |
| Rủi ro migration | JDK/API removal, module, classfile, behavior | API/server version, external dependency | Chuyển namespace, implementation và container generation |

Một dự án có thể **đồng thời dùng Java SE và Jakarta EE**. Chúng không phải hai lựa chọn loại trừ nhau. Jakarta EE application vẫn chạy trên nền tảng Java SE.

~~~mermaid
flowchart TD
    A["Application Java"] --> B["Java SE / JDK runtime"]
    A --> C["Enterprise API: Java EE hoặc Jakarta EE"]
    C --> D["Implementation / provider / container"]
    D --> B
    A --> E["Third-party libraries"]
    E --> B
~~~

## 3. Phân biệt API với implementation và runtime container

Một **đặc tả/API** định nghĩa các type và hành vi được cam kết. Một **implementation/provider** thực thi những hành vi đó. Một **application server hoặc embedded container** có thể đóng gói API, provider và vòng đời ứng dụng.

Ví dụ:

| Hợp đồng | API type ví dụ | Implementation/runtime |
|---|---|---|
| Servlet | `jakarta.servlet.http.HttpServlet` | Tomcat, Jetty hoặc servlet container phù hợp |
| Persistence | `jakarta.persistence.EntityManager` | Hibernate ORM, EclipseLink |
| Validation | `jakarta.validation.Validator` | Hibernate Validator hoặc provider phù hợp |
| REST (JAX-RS) | `jakarta.ws.rs.GET` | Jersey, RESTEasy hoặc implementation khác |
| CDI | `jakarta.enterprise.inject.spi.CDI` | Weld, OpenWebBeans, server tương ứng |
| XML Binding | `jakarta.xml.bind.JAXBContext` | JAXB runtime/provider |
| Mail | `jakarta.mail.Session` | Mail provider/runtime phù hợp |
| Transactions | `jakarta.transaction.UserTransaction` | Transaction manager/container |
| Messaging | `jakarta.jms.Message` | JMS provider/broker integration |

Việc một artifact tên `*-api.jar` chứa class/interface/annotation để biên dịch **không có nghĩa** ứng dụng đã có engine xử lý request, validate, persist hay serialize ở runtime.

Ngược lại, trong một application server đúng thế hệ, container có thể đã cung cấp API và implementation. Đóng thêm những JAR khác version vào WAR có thể tạo xung đột class loader. Do đó, mỗi migration cần trả lời:

1. Đây là API của Java SE, Java EE, Jakarta EE hay thư viện bên thứ ba?
2. Ai cung cấp **API class** cho compile?
3. Ai cung cấp **implementation** cho runtime?
4. Ai bootstrap/chọn provider?
5. Ai sở hữu version: ứng dụng, framework BOM, container hay server?
6. Mô hình triển khai là WAR lên server ngoài hay executable JAR có embedded runtime?

## 4. Vì sao Java 8 chạy được JAXB/JAX-WS mà Java 11 có thể lỗi?

Một nguồn hiểu nhầm quan trọng là các module Java EE/CORBA **từng được bundle trong một số JDK** như JDK 8, sau đó bị tách khỏi JDK.

JEP 320 loại bỏ các module Java EE và CORBA liên quan khỏi **JDK 11**. Trong số những module từng có ở JDK 9/10 và bị loại gồm:

- `java.xml.bind` (JAXB).
- `java.xml.ws` (JAX-WS).
- `java.activation` (JavaBeans Activation Framework).
- `java.xml.ws.annotation`.
- `java.corba`.
- `java.transaction`.
- Các tool module liên quan `jdk.xml.bind` và `jdk.xml.ws`.

Đây **không** phải tuyên bố toàn bộ nền tảng Java EE từng là một phần JDK; Servlet, JPA, CDI và nhiều enterprise API khác không được tự động cung cấp như một phần JDK Java SE.

### 4.1. Biểu hiện với JAXB cũ

Một hệ thống Java 8 có thể viết:

~~~java
import javax.xml.bind.JAXBContext;

JAXBContext context =
        JAXBContext.newInstance(Customer.class);
~~~

Khi chuyển sang JDK 11+ mà không bổ sung dependency, compile có thể báo:

~~~text
package javax.xml.bind does not exist
~~~

hoặc ứng dụng cũ chạy ở runtime mới có thể gặp:

~~~text
java.lang.NoClassDefFoundError: javax/xml/bind/JAXBContext
~~~

Giải pháp cần xác định **thế hệ API cần giữ** và **implementation tương ứng**:

- Nếu đang giữ source `javax.xml.bind.*`, chọn bộ API/runtime còn hỗ trợ namespace đó theo mục tiêu migration.
- Nếu chuyển source sang `jakarta.xml.bind.*`, dùng API và runtime thuộc thế hệ Jakarta tương thích.
- Không chỉ thêm một file có tên “jaxb” bất kỳ.
- Kiểm tra framework, generated classes, annotation và schema tooling liên quan.

### 4.2. Hai việc không được đánh đồng

**Việc A — JDK không còn bundle API cũ:** bổ sung đúng external dependency để thay khả năng trước đây do JDK cung cấp.

**Việc B — chuyển từ `javax.*` sang `jakarta.*`:** đổi source, dependency, implementation, framework và deployment generation khi kế hoạch yêu cầu.

Có trường hợp chỉ cần làm A để tiếp tục chạy trong giai đoạn migration; có trường hợp chiến lược sản phẩm yêu cầu cả A và B. Chuyển JDK lên Java 17/21 **không tự bắt buộc** mọi source đổi sang `jakarta.*`.

## 5. Lịch sử chuyển giao và namespace: những mốc dễ nhầm

| Giai đoạn | Điều cần nhớ |
|---|---|
| Java EE trước khi chuyển giao | Các enterprise APIs chủ yếu nằm dưới `javax.*` |
| Java EE 8 | Một thế hệ Java EE quan trọng trước Jakarta |
| Jakarta EE 8 | Tên nền tảng Jakarta; API namespace cơ bản vẫn `javax.*` |
| Jakarta EE 9 | Bước chuyển lớn nhiều enterprise package sang `jakarta.*` |
| Jakarta EE 9.1 và các phiên bản sau | Tiếp tục các phiên bản nền tảng Jakarta và nâng baseline/đặc tả theo từng release |
| JDK 11 | Các module Java EE/CORBA được bundle trước đó bị loại theo JEP 320 |

Không nên kết luận “cứ thấy Jakarta EE thì package chắc chắn là `jakarta.*`”: Jakarta EE 8 là phản ví dụ rõ ràng.

Ngược lại, nếu dependency thế hệ Jakarta EE 9+ yêu cầu `jakarta.servlet.*` mà mã nguồn vẫn import `javax.servlet.*`, chúng không phải cùng một class chỉ nhờ đặt cả hai JAR lên classpath.

### 5.1. Không đổi mọi javax thành jakarta

Một số API `javax.*` vẫn thuộc Java SE và phải giữ nguyên:

~~~java
import javax.crypto.Cipher;
import javax.net.ssl.SSLContext;
import javax.sql.DataSource;
import javax.annotation.processing.Processor;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.management.MBeanServer;
~~~

Với các API trên, tìm–thay toàn bộ `javax.` → `jakarta.` sẽ làm hỏng source.

Quy tắc chuyển đổi phải dựa trên **danh sách đặc tả/package enterprise thực sự được đổi tên**, không dựa trên tiền tố một cách mù quáng.

## 6. Ví dụ Servlet: compiler, server và namespace

### 6.1. Source ở thế hệ cũ

~~~java
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

import java.io.IOException;

public class LegacyHealthServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response) throws IOException {
        response.getWriter().write("OK");
    }
}
~~~

Mã này phụ thuộc Servlet API `javax.servlet.*` và cần servlet container phù hợp với generation đó. JDK Java SE một mình không cung cấp servlet engine.

### 6.2. Source sau khi chuyển sang Jakarta generation

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
        response.getWriter().write("OK");
    }
}
~~~

Trong mã Jakarta, `jakarta.servlet.http.HttpServlet` có tên bytecode khác với `javax.servlet.http.HttpServlet`. Cần Servlet API và container đúng thế hệ.

Chuyển source import chưa đủ nếu:

- Filter/listener khác vẫn dùng `javax.servlet.*`.
- Framework MVC, security hoặc file upload extension được build cho namespace cũ.
- Annotation, descriptor `web.xml` hoặc component scanning còn metadata cũ.
- Container chạy thuộc generation chưa hỗ trợ API mới.
- WAR chứa trùng Servlet API không phù hợp với server.

### 6.3. Vì sao binary compatibility bị phá

Bytecode của một class có thể chứa symbolic reference:

~~~text
javax/servlet/http/HttpServlet
~~~

Bản Jakarta mới có class:

~~~text
jakarta/servlet/http/HttpServlet
~~~

Đây là hai **binary names** khác nhau. JVM không tự tạo alias giữa chúng. Thêm JAR Jakarta không làm một class đã compile với javax tự chuyển reference.

Một số công cụ chuyển đổi bytecode/resource có thể hỗ trợ migration trong phạm vi được công bố, nhưng phải kiểm chứng output và giới hạn của công cụ. Không giả định một thao tác rename package là đủ cho mọi annotation, reflection string, config file và dependency.

## 7. Ví dụ Persistence: annotation cũng cần cùng thế hệ provider

Entity dùng Java EE/Jakarta EE 8:

~~~java
import javax.persistence.Entity;
import javax.persistence.Id;

@Entity
public class LegacyOrder {
    @Id
    private Long id;
}
~~~

Entity dùng Jakarta EE 9+:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class Order {
    @Id
    private Long id;
}
~~~

Với provider không hỗ trợ annotation `jakarta.persistence.Entity`, entity có thể không được nhận diện. Ngược lại, một provider Jakarta mới có thể không xử lý entity cũ với `javax.persistence.Entity` theo cùng cách.

Lỗi biểu hiện có thể là:

- Không tìm được persistence unit/provider.
- Entity không được quản lý.
- Lỗi mapping hoặc bootstrap.
- Thiếu class/method do API/provider lệch version.
- DataSource hoặc JDBC driver không có dù JPA API hiện diện.

Cách xử lý:

1. Xác định JPA API generation.
2. Chọn provider version tương thích.
3. Kiểm tra framework integration.
4. Cập nhật import và annotation trên entity, converter/listener.
5. Kiểm tra `persistence.xml` và service registration nếu được dùng.
6. Kiểm tra DB migrations và schema.
7. Chạy integration test trên database thực tế.

### 7.1. Jakarta Persistence không đồng nghĩa JDBC

JDBC interfaces như `java.sql.Connection` và `javax.sql.DataSource` thuộc Java SE. Khi nâng JPA từ javax sang Jakarta, **không đổi `javax.sql.DataSource` thành `jakarta.sql.DataSource`**.

Một stack hợp lệ có thể kết hợp `jakarta.persistence.EntityManager` với `javax.sql.DataSource` và `java.sql.Connection`. Đây là ví dụ rõ ràng cho thấy ranh giới chuẩn phải được hiểu theo **vai trò API**, không theo tiền tố package.

## 8. Jakarta Validation, CDI và JAX-RS

### 8.1. Jakarta Validation

Một DTO Jakarta có thể dùng:

~~~java
import jakarta.validation.constraints.NotBlank;

public record CreateCustomer(
        @NotBlank String name) {
}
~~~

Annotation chỉ mô tả constraint. Cần provider như một validation implementation tương thích và điểm kích hoạt validation trong ứng dụng/framework.

Nếu thiếu runtime provider, `@NotBlank` có thể vẫn compile, nhưng việc bootstrap `jakarta.validation.Validation` sẽ không hoạt động như mong đợi.

Khi chuyển từ `javax.validation.*` sang `jakarta.validation.*`:

- Đổi imports của annotations và types.
- Căn provider version.
- Kiểm tra framework/starter.
- Kiểm thử constraint thực sự bị vi phạm.
- Xem generated source, custom validators và exception mappers.

### 8.2. CDI

CDI không chỉ là `@Inject`. Container còn quản lý bean discovery, scopes, interceptors, events và lifecycle.

Một ứng dụng độc lập có annotation CDI nhưng không bootstrap CDI container không tự có dependency injection chỉ nhờ JDK. Nếu application server đã cung cấp CDI thì packaging và scope dependency có thể khác ứng dụng standalone.

Khi migration, xem:

- Namespace của injection/CDI annotations.
- Bean archive discovery.
- `beans.xml` khi có.
- Interceptor/decorator/extension code.
- API/provider/container version.
- Module opens và reflection access nếu chạy JPMS.

### 8.3. JAX-RS

Một REST resource:

~~~java
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;

@Path("/health")
public class HealthResource {
    @GET
    @Produces(MediaType.TEXT_PLAIN)
    public String health() {
        return "OK";
    }
}
~~~

API `jakarta.ws.rs.*` định nghĩa annotation và contract. Runtime JAX-RS provider/framework phải bootstrap routing và HTTP integration.

Nếu application dùng Spring MVC annotations chứ không dùng JAX-RS, không nên tự thêm JAX-RS implementation chỉ vì cả hai đều làm REST. Xác định rõ framework thực tế sử dụng.

## 9. Java EE/Jakarta EE không đồng nghĩa Spring

Nhiều dự án dùng Spring Framework hoặc Spring Boot mà không chạy một application server Java EE/Jakarta EE đầy đủ.

Một số khả năng:

- Spring MVC chạy trên embedded servlet container.
- Spring Boot executable JAR mang container và provider cần thiết.
- Spring ứng dụng đóng WAR để triển khai vào external container.
- Spring Data JPA tích hợp với một persistence provider.
- Spring dùng Jakarta EE APIs ở một số lớp nhưng không cần một Jakarta EE full platform implementation.

Vì vậy, ba câu “chạy Java”, “dùng Jakarta Servlet API” và “là Jakarta EE application đầy đủ” không có nghĩa giống nhau.

### 9.1. Framework major version thường ràng buộc namespace

Một thế hệ framework có thể dựa trên `javax.*` enterprise APIs; thế hệ mới có thể chuyển sang `jakarta.*`. Trong migration, cần đối chiếu **compatibility matrix** của framework, JDK, container và API generation.

Không thể chỉ nâng JDK, giữ framework cũ rồi tự đổi toàn bộ entity/servlet imports mà không kiểm tra khả năng hỗ trợ của framework.

### 9.2. Đừng thêm application server dependency vào mọi executable JAR

Một ứng dụng standalone chỉ cần embedded server và provider mà framework lựa chọn. Đóng nhiều container/Jakarta platform implementations vào cùng artifact không giúp tăng tương thích và có thể gây classpath conflict, service discovery ambiguity và tăng bề mặt bảo trì.

## 10. Java EE server, Jakarta EE server và embedded container

### 10.1. External application server

Một WAR được triển khai lên server ngoài có thể dựa vào server cung cấp API và implementation theo profile/đặc tả server hỗ trợ.

Ví dụ Maven cho API Servlet được container cung cấp:

~~~xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <version>VERSION_MATCHING_SERVER</version>
    <scope>provided</scope>
</dependency>
~~~

`VERSION_MATCHING_SERVER` là placeholder minh họa, phải thay bằng version tương thích thực tế.

**`provided` không có nghĩa API không cần runtime.** Nó có nghĩa build kỳ vọng server/container bên ngoài cung cấp dependency thích hợp.

### 10.2. Embedded server

Ứng dụng tự chạy `java -jar application.jar` cần có embedded HTTP/servlet engine nếu thiết kế sử dụng servlet web stack.

Lúc đó, chỉ để Servlet API `provided` mà không có embedded container ở runtime có thể không đủ. Một framework starter có thể đã kéo container transitively; cần xem runtimeClasspath và artifact phát hành.

### 10.3. Full platform và các profile

Các nền tảng Java EE/Jakarta EE có các tập đặc tả/profile khác nhau tùy phiên bản. Một server hỗ trợ một profile không nhất thiết cung cấp mọi API của toàn nền tảng.

Trước khi bỏ dependency khỏi WAR vì tin “server chắc chắn có”, cần xem server **phiên bản nào, profile nào và các service nào thực sự được cung cấp**.

### 10.4. Class loader isolation và duplicate APIs

Một JAR API được đóng trong `WEB-INF/lib` có thể xung đột với bản container đã cung cấp. Trên JVM, class identity không chỉ là binary name mà còn liên quan tới defining class loader.

Hai class cùng tên nhưng do hai loader độc lập định nghĩa có thể không cast được sang nhau, dẫn tới `ClassCastException` hoặc các lỗi linkage. Điều tra cần xác minh class được nạp từ đâu, không chỉ xem dependency tree.

## 11. Maven: scope theo ranh giới của nền tảng

Một ứng dụng WAR:

~~~xml
<dependencies>
    <dependency>
        <groupId>jakarta.servlet</groupId>
        <artifactId>jakarta.servlet-api</artifactId>
        <version>SERVLET_API_VERSION</version>
        <scope>provided</scope>
    </dependency>

    <dependency>
        <groupId>jakarta.persistence</groupId>
        <artifactId>jakarta.persistence-api</artifactId>
        <version>PERSISTENCE_API_VERSION</version>
    </dependency>
</dependencies>
~~~

Đây là **cú pháp mẫu**, không phải POM production hoàn chỉnh: JPA API có thể do server cung cấp trong mô hình Jakarta EE server, hoặc do ứng dụng cùng provider mang theo. Scope cần quyết định theo deployment.

| Scope Maven | Vai trò khi migration |
|---|---|
| `compile` | API có ở compile và thường runtime |
| `provided` | API cần compile nhưng do server/container cung cấp lúc chạy |
| `runtime` | Provider/driver cần lúc chạy nhưng không cần import ở compile |
| `test` | Dependency/implementation chỉ phục vụ test |
| BOM `import` trong `dependencyManagement` | Quản lý version, không tự thêm implementation vào runtime |

Một BOM Jakarta EE hoặc framework có thể điều phối version, nhưng **BOM không tự cài provider**. Cần khai báo những dependency được sử dụng thực tế.

### 11.1. Không thay thế bằng một “mega JAR” không kiểm soát

Thêm đồng thời mọi thư viện API Java EE, Jakarta EE và provider khác nhau để chữa lỗi có thể gây:

- Trùng class/namespace.
- API và implementation khác generation.
- ServiceLoader chọn provider khác dự kiến.
- Lệch transitive dependencies.
- Xung đột container và logging.
- JDK runtime baseline không còn phù hợp.

Thay vào đó, hãy lập danh sách từng API được sử dụng và ai cung cấp implementation.

## 12. Gradle: compileOnly, implementation, runtimeOnly và api

Với Gradle, khai báo tùy mô hình:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    // Ví dụ API do external servlet container cung cấp:
    compileOnly("jakarta.servlet:jakarta.servlet-api:SERVLET_VERSION")

    // API được code ứng dụng sử dụng:
    implementation("jakarta.persistence:jakarta.persistence-api:JPA_VERSION")

    // Provider thực thi persistence trong mô hình standalone:
    runtimeOnly("org.example:orm-provider:PROVIDER_VERSION")
}
~~~

Tọa độ `org.example` và `*_VERSION` là placeholder. Không sao chép trực tiếp vào build thật. Với Gradle Java Library plugin, dùng `api(...)` nếu một dependency type lộ qua **public contract** của thư viện và consumer cần nó ở compile classpath.

Điểm quan trọng:

- `compileOnly` không tự đưa API vào runtime.
- `runtimeOnly` không làm class có sẵn cho source compile.
- `implementation` có ở compile/runtime của module nhưng không đồng nghĩa public API export cho compile consumer.
- `api` công bố dependency cho consumer dùng public contract.
- Test source set có classpath khác với production và không nên được xem là bằng chứng packaging production.

Cần kiểm tra:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

Các lệnh trên là ví dụ để người học chạy tại dự án phù hợp, không phải lệnh đã được thực hiện trong quá trình viết tài liệu.

## 13. Migration không phải chỉ là sửa import

Thay `javax.servlet` bằng `jakarta.servlet` có thể làm một file compile, nhưng còn nhiều ràng buộc khác.

### 13.1. Code nguồn

Tìm trong:

- Application source, test source.
- Filter/listener/interceptor.
- Controller/resource classes.
- Entity, converter, validator, event listener.
- Custom annotation processors.
- Generated source.
- Utility library có public type chứa API enterprise cũ.

### 13.2. Binary dependencies

Một JAR đã compile với `javax.persistence.EntityManager` vẫn tham chiếu đúng binary name đó dù source ứng dụng đã đổi. Có thể cần nâng hoặc thay dependency, hoặc dùng biến đổi được hỗ trợ.

### 13.3. XML descriptors và tài nguyên

Các enterprise application có thể dùng:

- `web.xml`.
- `persistence.xml`.
- `beans.xml`.
- Descriptor của server/vendor.
- Tag library descriptor.
- Service loader files ở `META-INF/services`.
- File cấu hình chứa tên lớp Java dạng chuỗi.
- Reflection configuration cho native-image.

Một số descriptor dùng schema namespace/version riêng. Thay Java imports không tự cập nhật XML schema hay cấu hình server.

### 13.4. Annotation và reflection

An annotation processor, scanner hoặc framework có thể tìm annotation `javax.*` bằng đúng class name. Sau khi đổi annotation sang `jakarta.*`, scanner cũ có thể bỏ qua class mà không báo compile error.

Cần thử **chức năng thực tế**: request routing, persistence, validation, injection, serialization.

### 13.5. Service Provider Interface

Một số API dùng `ServiceLoader` hoặc provider discovery thông qua file trong `META-INF/services`. Khi interface được đổi từ `javax...` sang `jakarta...`, tên service descriptor cũng có thể cần cập nhật theo API mới.

Provider JAR có mặt nhưng service file sai có thể dẫn tới “không tìm thấy provider”. Shading/fat JAR còn có thể làm mất service files.

## 14. Source compatibility, binary compatibility và runtime compatibility

| Tầng tương thích | Câu hỏi | Ví dụ lỗi |
|---|---|---|
| Source | Source compile lại với API mới được không? | `package javax.servlet does not exist` |
| Binary | Bytecode cũ có resolve các type/method như trước? | `NoClassDefFoundError`, `NoSuchMethodError` |
| Runtime provider | Có implementation thực thi API đang dùng không? | Validation/JSON/JAXB provider not found |
| Container | Server/embedded runtime hỗ trợ đúng generation? | Servlet class mismatch |
| Deployment metadata | Descriptor, resource, service registry đúng? | Không đăng ký route/bean/entity |
| Behavior | Thao tác có cùng ngữ nghĩa không? | Mapping, transaction, validation thay đổi |
| Data protocol | JSON/XML/database contract có giữ được không? | Serializer output đổi hoặc consumer parse thất bại |
| JDK compatibility | API/provider chạy trên JDK mục tiêu? | `UnsupportedClassVersionError` |

Một hệ thống có thể đạt **source compatibility** nhưng vẫn sai ở runtime. Hoặc một ứng dụng giữ namespace `javax.*` vẫn có thể chạy trên JDK mới nếu dùng stack enterprise cũ có hỗ trợ runtime đó và phụ thuộc được khai báo đầy đủ.

### 14.1. Tại sao tên kiểu khác nghĩa là thay đổi lớn

Ví dụ method public:

~~~java
// Hợp đồng cũ
void handle(javax.servlet.http.HttpServletRequest request);

// Hợp đồng mới
void handle(jakarta.servlet.http.HttpServletRequest request);
~~~

Method descriptor ở class file khác nhau vì tham số có binary name khác. Với consumer đã compile trước đó, method mới **không phải** cùng descriptor với method cũ; có thể gây `NoSuchMethodError` khi gọi phương thức từ library bị thay.

Cần đánh giá binary consumer độc lập nếu thư viện đang phát hành public API cho nhiều dịch vụ.

## 15. Định danh lỗi để không chữa sai tầng

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra |
|---|---|---|
| `package javax.xml.bind does not exist` | JDK mới không còn bundled JAXB API hoặc compile dependency thiếu | API generation, JDK/module, Maven/Gradle |
| `package jakarta.persistence does not exist` | Jakarta Persistence API chưa ở compile classpath | Dependency và namespace |
| `NoClassDefFoundError: javax/servlet/...` | Runtime thiếu thế hệ Servlet API cũ | WAR/container, binary dependency |
| `NoSuchMethodError` | API/provider hoặc framework lệch binary version | Descriptor và dependency graph |
| `AbstractMethodError` | Implementation không đáp ứng method runtime mong đợi | Version API/provider |
| `ClassCastException` | Duplicate API class hoặc khác classloader | Class loading và server libraries |
| `ValidationException` khi bootstrap | Thiếu/sai validation provider hoặc config | Provider discovery, generation |
| JAXB provider not found | Có API, thiếu runtime implementation hoặc metadata | JAXB runtime và service files |
| HTTP 404 dù servlet compile | Container/registration/descriptor không khớp | Runtime logs, route mappings |
| Entity not managed | Annotation/provider/scanning sai thế hệ | Persistence bootstrap và metadata |
| `ServiceConfigurationError` | SPI/provider resource sai | Service file/module declarations |
| `UnsupportedClassVersionError` | Artifact yêu cầu JDK mới hơn runtime | Class major version, JDK baseline |

Không có lỗi nào ở bảng trên chứng minh nguyên nhân một cách tuyệt đối. Cần xem stack trace đầy đủ, các cause lồng nhau và **JAR thực tế đã được nạp**.

### 15.1. Phân biệt thiếu API với thiếu implementation

Ví dụ mã:

~~~java
import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;

ValidatorFactory factory =
        Validation.buildDefaultValidatorFactory();
~~~

Nếu `Validation` class không có: lỗi thiếu **API/runtime class**.

Nếu class có nhưng bootstrap không tìm provider: lỗi thiếu **implementation/discovery/configuration**.

Nếu provider đã được tìm nhưng lỗi linkage: có thể là **version mismatch**. Thêm một API JAR khác generation không phải giải pháp có căn cứ.

## 16. Tìm điểm sử dụng API enterprise trước khi migration

Một số gợi ý tìm kiếm:

~~~bash
rg -n "import javax\\.(servlet|persistence|validation|ws|enterprise|ejb|jms|transaction|mail|xml\\.bind)" src
rg -n "import jakarta\\." src
rg -n "javax\\.|jakarta\\." src/main/resources
rg -n "web\\.xml|persistence\\.xml|beans\\.xml" .
rg -n "META-INF/services|ServiceLoader" .
~~~

Các câu lệnh chỉ minh họa cách điều tra trong repository, không phải một bộ pattern đủ bao phủ mọi API. Tìm thêm:

- Test fixtures.
- Java source được sinh.
- JSP/tag libraries.
- Build plugin configurations.
- Reflection strings và class names trong XML/YAML/properties.
- Artifacts đã đóng gói.
- Dependency thuộc sở hữu đội khác.

Không nên dùng replace-all `javax.` vì nó có thể phá Java SE API.

### 16.1. Kiểm tra dependency tree

Maven:

~~~bash
mvn dependency:tree
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jakarta.servlet \
  --configuration runtimeClasspath
~~~

Cần xác định API Java EE/ Jakarta EE cũ có được kéo qua dependency bắc cầu không, và framework hoặc server nào đang quản lý version.

### 16.2. Kiểm tra class trong artifact

~~~bash
jar tf application.war
jar tf library.jar
javap -classpath library.jar -p -s com.example.PublicApi
~~~

`javap -s` giúp xem method descriptor còn chứa binary name `javax/...` hay đã chuyển sang `jakarta/...`. Với WAR, kiểm tra `WEB-INF/lib` và container libraries để tránh trùng API/runtime.

### 16.3. Kiểm tra jdeps

~~~bash
jdeps --recursive --class-path "lib/*" application.jar
~~~

`jdeps` hỗ trợ phân tích static class/module dependencies. Nó không thấy mọi reflection string hoặc SPI provider nạp động, nên phải kết hợp kiểm thử runtime. Với executable JAR có nested libraries, có thể cần extract/điều chỉnh classpath để phân tích đúng.

## 17. Lập ma trận chuyển đổi trước khi nâng cấp

Mỗi dự án nên có bảng tương tự:

| Thành phần | Hiện tại | Mục tiêu | Ai cung cấp runtime? | Hành động |
|---|---|---|---|---|
| JDK | JDK cũ | JDK mục tiêu | JDK distribution | Xác minh Java SE support và modules |
| Servlet | `javax.servlet` | `jakarta.servlet` hoặc giữ tạm | External/embedded container | Nâng đồng bộ container/framework |
| Persistence | `javax.persistence` | `jakarta.persistence` hoặc giữ tạm | ORM/server | Căn API/provider và entity metadata |
| Validation | `javax.validation` | `jakarta.validation` | Provider/server | Test constraints và bootstrap |
| REST API | JAX-RS javax | Jakarta REST | JAX-RS provider | Test resource registration |
| JAXB/JAX-WS | JDK-bundled/legacy | External dependency phù hợp | Application/provider | Tách vấn đề JDK removal với namespace |
| JDBC | `java.sql`/`javax.sql` | Giữ Java SE API | JDK + JDBC driver | Không đổi namespace |
| Cryptography | `javax.crypto` | Giữ Java SE API | JDK/security provider | Không đổi namespace |

Với mỗi hàng, cần ghi thêm version, JDK baseline, compatibility guide, owner, test coverage và phương án rollback.

### 17.1. Quyết định lộ trình: giữ javax tạm thời hay chuyển Jakarta?

Không phải lúc nào nhóm cũng phải chuyển namespace cùng ngày nâng JDK.

**Lộ trình A — nâng JDK trước, giữ enterprise generation cũ:** phù hợp khi framework và provider vẫn hỗ trợ JDK mục tiêu. Cần khai báo explicit các dependency bị loại khỏi JDK và kiểm tra bảo mật/hỗ trợ của stack.

**Lộ trình B — chuyển toàn bộ enterprise stack sang Jakarta:** phù hợp khi framework/container mục tiêu yêu cầu `jakarta.*`. Cần thay source imports, binary dependencies, annotation/resource metadata, provider và deployment.

**Lộ trình C — tách theo module/service:** áp dụng khi các service triển khai độc lập. Mỗi service phải có stack nội bộ nhất quán; giao tiếp qua HTTP/JSON/event schema hoặc API tương thích, thay vì truyền trực tiếp object types `javax.*` ↔ `jakarta.*` trên một classpath và hy vọng JVM chuyển đổi tự động.

Không nên giữ enterprise stack đã hết hỗ trợ trong thời gian dài chỉ để tránh thay đổi. Quyết định cần cân nhắc security support, dependency lifecycle và chi phí migration.

## 18. Quy trình chuyển đổi có kiểm soát

~~~mermaid
flowchart TD
    A["Inventory JDK, API, provider, framework, server"] --> B["Phân loại Java SE / Java EE / Jakarta EE"]
    B --> C["Chọn JDK và enterprise generation mục tiêu"]
    C --> D["Nâng framework, provider và container đồng bộ"]
    D --> E["Chỉnh source/import/annotation/descriptor"]
    E --> F["Build và inspect dependency graph / artifact"]
    F --> G["Chạy integration tests thực"]
    G --> H{"Đúng chức năng và tương thích?"}
    H -->|Có| I["Rollout có kiểm soát và lưu bằng chứng"]
    H -->|Không| J["Khoanh lỗi classpath / provider / schema"]
    J --> D
~~~

### Bước 1. Khóa baseline

Ghi:

- JDK vendor/version.
- Framework và application server version.
- Các API enterprise đang dùng.
- Các provider triển khai.
- Cách đóng gói JAR/WAR/EAR và class loader.
- Dependency graph và artifact checksum.
- Kết quả test hiện tại.
- API contract và client/service bên ngoài có liên quan.

### Bước 2. Xác định đích

Chọn JDK runtime cùng enterprise API generation và server/provider được hỗ trợ. Không dùng việc “JDK có cài được trên máy” làm bằng chứng server/framework cũng hỗ trợ JDK đó.

### Bước 3. Cập nhật dependencies và BOM

Căn framework, API, provider, build plugin và container theo compatibility matrix của dự án. Loại bỏ API/provider cũ chỉ khi đã xác định thay thế. Tránh hai generation trộn trong cùng một ứng dụng trừ khi có giải pháp phân tách được thiết kế rõ.

### Bước 4. Chuyển source và metadata

Cập nhật enterprise imports, annotations, XML descriptors, service descriptors, generated source và reflection strings. Giữ nguyên Java SE `javax.*`.

### Bước 5. Biên dịch sạch

Chạy clean build trong CI bằng JDK/toolchain mục tiêu, xác minh annotation processors và generated classes. Đừng để output cũ che lỗi migration.

### Bước 6. Thử bootstrap và chức năng thực

Cần kiểm tra:

- HTTP request qua servlet/filter.
- Bean dependency injection và lifecycle.
- JPA entity scanning, SQL, transaction.
- Validation constraint thất bại đúng chỗ.
- JAX-RS route và serialization.
- JAXB/JAX-WS hoặc Mail khi có dùng.
- Logging/security/TLS.
- Ứng dụng đóng gói và triển khai lên server/container đích.

### Bước 7. Thử consumer cũ và mới

Nếu public library thay namespace trong method signatures, consumer đã compile cũ có thể không tương thích. Có thể cần major release, adapter hoặc migration theo nhóm.

Các wire protocols (JSON, XML, database) cũng cần kiểm thử: việc đổi namespace Java **không tự buộc** JSON schema hoặc XML document format thay đổi, nhưng implementation mới có thể đổi default behavior.

### Bước 8. Triển khai và giám sát

Ghi rõ canary/rollback criteria: lỗi startup/DI, HTTP 5xx, persistence mapping, validation failures, payload schema errors, provider resolution và latency. Thu thập dữ liệu theo artifact/version, không chỉ dựa vào một câu “đã nâng JDK”.

## 19. Kiểm thử ma trận theo từng môi trường

| Tình huống | API generation | Runtime | Điều cần xác minh |
|---|---|---|---|
| Baseline | Java EE/Jakarta EE cũ | Server/JDK cũ | Chức năng và lỗi đã biết |
| JDK upgrade only | API generation cũ | JDK mới, runtime cũ được hỗ trợ | Có thể tách lỗi JDK removal/behavior |
| Enterprise upgrade | Jakarta thế hệ mới | Framework/server mới | Source/metadata/provider compatibility |
| WAR production | API được đánh dấu provided | External container | Class loader, servlet boot, resources |
| Embedded JAR | API và server runtime tích hợp | JDK target | Packaging, endpoint và dependency |
| Consumer cũ | Biên dịch với API cũ | Library mới | Binary compatibility hoặc migration |
| Consumer compile lại | API mới | Runtime mới | Source compatibility |
| Data integration | Có thể khác generation nội bộ | HTTP/JSON/XML/DB | Wire contract được bảo toàn |

Các bài test nên chạy trên **JAR/WAR phát hành thực tế**, đúng JDK và server/container image, thay vì chỉ compile module từ IDE.

## 20. Một tình huống migration tổng hợp

Giả sử hệ thống quản lý đơn hàng ban đầu:

- Chạy JDK 8.
- Đóng WAR triển khai trên một Servlet container thuộc thế hệ `javax.servlet`.
- Dùng `javax.persistence` và ORM provider cũ.
- Dùng JAXB `javax.xml.bind` cho XML integration.
- Dùng `javax.sql.DataSource` để cấu hình connection pool.
- Dùng validation annotations `javax.validation`.
- Có thư viện bên ngoài đã compile với những enterprise APIs cũ.

Nhóm muốn chạy trên JDK mới và dùng framework/controller thế hệ Jakarta.

**Các vấn đề nếu nâng thiếu đồng bộ:**

1. Bỏ JDK 8, JAXB không còn đến từ JDK mục tiêu.
2. Chỉ đổi import Servlet mà vẫn triển khai trên container thế hệ cũ.
3. Đổi Entity annotation sang `jakarta.persistence` nhưng dùng ORM provider chỉ hiểu javax.
4. Chuyển `javax.sql.DataSource` thành một package Jakarta không tồn tại.
5. Thêm cả hai Servlet API để tránh compile error nhưng tạo classloader conflict.
6. Không nâng thư viện tích hợp cũ, dẫn tới binary method signature `javax.servlet.*` còn trong JAR.
7. Quên `web.xml` hoặc các tài nguyên/provider metadata.
8. Test unit xanh nhưng runtime không đăng ký servlet hoặc không nhận entity.

**Kế hoạch phù hợp:**

- Lập inventory chính xác API nào thuộc Java SE và enterprise.
- Giữ `javax.sql.DataSource` vì là Java SE.
- Quyết định cụ thể JAXB sẽ giữ thế hệ javax tạm thời hay chuyển Jakarta, rồi chọn runtime tương ứng.
- Nâng Servlet API, container và framework cùng generation.
- Nâng JPA API và ORM provider đồng bộ, chạy test persistence.
- Nâng validation provider và test constraint thật.
- Kiểm tra mã nguồn, bytecode dependency và XML/service descriptors.
- Đóng gói WAR/JAR theo mô hình runtime được chọn.
- Chạy test end-to-end với database/XML/HTTP trên JDK mới.
- Triển khai canary và theo dõi lỗi classloader/provider/data.

Điểm quan trọng: có thể cần **một kế hoạch nâng JDK** và **một kế hoạch nâng enterprise platform** liên quan nhưng tách biệt để dễ kiểm soát rủi ro.

## 21. Các sai lầm thường gặp

### 21.1. “javax nghĩa là Java EE, nên phải đổi hết sang jakarta”

Sai. `javax.crypto`, `javax.sql`, `javax.net.ssl`, `javax.annotation.processing` và `javax.xml.parsers` là những ví dụ Java SE vẫn dùng `javax.*`.

### 21.2. “Nâng JDK lên 21 tức là đã dùng Jakarta EE”

Sai. JDK là runtime Java SE; enterprise APIs/providers là layer khác. Phải chọn dependency hoặc runtime enterprise rõ ràng.

### 21.3. “Java EE bị xóa khỏi JDK 11”

Cách nói này quá rộng. JDK 11 loại bỏ **một số module Java EE/CORBA từng được bundle**, không phải mọi đặc tả Java EE đều từng ở trong JDK.

### 21.4. “Jakarta EE 8 đã chuyển hoàn toàn sang jakarta.*”

Sai. Việc chuyển nhiều enterprise packages sang `jakarta.*` là bước thay đổi nổi bật của Jakarta EE 9.

### 21.5. “Thêm cả javax và jakarta API sẽ có adapter”

Sai. Hai type có binary name khác nhau; JVM không tự tạo bridge. Thư viện, provider và framework phải cùng generation hoặc dùng adapter chuyên biệt có hỗ trợ rõ.

### 21.6. “Chỉ cần đổi imports là xong”

Sai. Dependency nhị phân, annotation processor, runtime provider, descriptor, reflection strings và container cũng có thể phải chuyển.

### 21.7. “Có API là có thể chạy”

Sai. Servlet cần container; JPA cần provider; validation cần engine; JAXB cần runtime/provider trong mô hình phụ thuộc tương ứng.

### 21.8. “Scope provided có nghĩa dependency không cần ở runtime”

Sai. Nó nghĩa là component **bên ngoài ứng dụng** sẽ cung cấp. Nếu runtime không cung cấp, ứng dụng sẽ lỗi.

### 21.9. “Spring Boot chắc chắn là Jakarta EE server”

Không phải. Spring Boot có thể dùng các API Jakarta/Servlet và embedded server, nhưng đó không đồng nghĩa triển khai toàn bộ Jakarta EE platform.

### 21.10. “Một lần chạy local chứng minh migration tương thích”

Không đủ. Local có thể dùng JDK khác, classpath rộng hơn, IDE plugin, embedded provider khác hoặc test database không giống production.

## 22. Checklist phân biệt và chuyển đổi

### Nhận diện nền tảng

- [ ] Đã tách Java SE API khỏi enterprise API.
- [ ] Không đổi các Java SE `javax.*` thành `jakarta.*`.
- [ ] Đã xác định Java EE 8, Jakarta EE 8 và Jakarta EE 9+ khác nhau về namespace.
- [ ] Đã phân biệt JDK upgrade với enterprise platform/framework upgrade.
- [ ] Đã ghi rõ các module JEP 320 liên quan khi chuyển qua JDK 11+.

### Dependency và implementation

- [ ] Mỗi API có runtime implementation/provider được chỉ định.
- [ ] Đã biết application, embedded server hay external container cung cấp implementation.
- [ ] Đã căn version theo compatibility matrix của framework/server.
- [ ] Đã kiểm tra Maven scopes/Gradle configurations.
- [ ] Đã kiểm tra compileClasspath và runtimeClasspath, transitive dependencies.
- [ ] Đã loại duplicate hoặc provider thế hệ sai khi phù hợp.
- [ ] Đã kiểm tra JDK baseline của tất cả runtime dependencies.

### Source, binary và metadata

- [ ] Đã rà soát imports, annotation và public API signatures.
- [ ] Đã tìm enterprise `javax.*` trong thư viện đã compile, không chỉ source.
- [ ] Đã cập nhật XML descriptors và service/provider metadata cần thiết.
- [ ] Đã kiểm tra annotation processing và generated source.
- [ ] Đã phân biệt API không tìm thấy với implementation không tìm thấy.
- [ ] Đã kiểm tra class loading/JAR thực tế trong server runtime.
- [ ] Đã đánh giá consumer nhị phân cũ khi public API đổi namespace.

### Vận hành và dữ liệu

- [ ] Đã chạy application bootstrap trên target JDK/container.
- [ ] Đã kiểm thử servlet HTTP, CDI/DI, JPA/transaction, validation và JAX-RS nếu dùng.
- [ ] Đã kiểm thử JAXB/JAX-WS, messaging, Mail hoặc service provider nếu dùng.
- [ ] Đã kiểm tra JSON/XML/data contract qua producer/consumer versions.
- [ ] Đã thử với artifact đã đóng gói và server image mục tiêu.
- [ ] Đã lưu dependency graph, runtime version và test evidence.
- [ ] Đã có kế hoạch rollout và rollback.

## Kết luận

**Java SE** là nền tảng ngôn ngữ, thư viện lõi và runtime; **Java EE** là thế hệ đặc tả enterprise trước Jakarta; **Jakarta EE** tiếp nối các đặc tả đó, với bước chuyển namespace quan trọng từ `javax.*` sang `jakarta.*` ở Jakarta EE 9. Không phải mọi `javax.*` đều thuộc Java EE, và nâng JDK không tự động chuyển một ứng dụng sang Jakarta EE.

Khi migration, hãy phân loại **API nào từ JDK, API nào từ enterprise specification, ai cung cấp implementation và container, và generation nào được hỗ trợ**. Xử lý riêng việc các module từng được bundle trong JDK bị loại ở JDK 11 và việc chuyển namespace enterprise. Sau đó xác minh toàn bộ stack từ source, bytecode, dependency graph, descriptor đến chức năng runtime và giao thức dữ liệu. Cách tiếp cận này ngăn lỗi trộn `javax`/`jakarta`, thiếu provider và xung đột classloader, đồng thời giúp nâng Java có thể kiểm chứng và rollback.

