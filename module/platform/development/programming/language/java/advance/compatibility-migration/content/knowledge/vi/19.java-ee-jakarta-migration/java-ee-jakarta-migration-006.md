# Sửa import, annotation, XML descriptor và tên lớp trong cấu hình

Trong quá trình chuyển ứng dụng từ **Java EE** sang **Jakarta EE**, một thay đổi có thể nhìn rất đơn giản: thay `javax.servlet.http.HttpServlet` bằng `jakarta.servlet.http.HttpServlet`, hoặc đổi `javax.persistence.Entity` thành `jakarta.persistence.Entity`. Tuy nhiên, một dự án thực tế hiếm khi chỉ chứa mã Java có thể nhìn thấy trực tiếp. Tên class của framework có thể được ghi trong `web.xml`, `persistence.xml`, Spring metadata, `META-INF/services`, biến môi trường, cấu hình YAML, database hoặc mã sinh từ template. Nếu chỉ sửa `import` rồi kết thúc, application server hoặc framework có thể không khởi động, không tìm được provider, không nhận annotation, hoặc bỏ qua cấu hình triển khai.

Bài học thuộc chương **Java EE và Jakarta** của module **Java Advance Compatibility Migration**. Mục tiêu là hình thành quy trình chuyển đổi có kiểm soát cho **bốn lớp thông tin liên quan đến nhau**:

1. **Source import và fully qualified type name** trong Java/Kotlin/Groovy và mã sinh.
2. **Annotation và contract**: class annotation có cùng tên đơn giản nhưng thuộc hai hệ package khác nhau.
3. **XML descriptor**: namespace, schema location, version và nội dung tên class.
4. **Cấu hình runtime và service metadata**: các chuỗi dùng để nạp class, provider, filter, listener, persistence, dependency injection.

Điểm quan trọng: không được thay mọi chuỗi bắt đầu bằng `javax.` thành `jakarta.`. Nhiều package `javax.*` thuộc **Java SE** vẫn giữ nguyên và không nằm trong phạm vi chuyển đổi namespace Jakarta EE.

## 1. Phân biệt nâng JDK với nâng Jakarta EE

### 1.1. Java SE, Java EE và Jakarta EE không phải cùng một phiên bản

**Java SE** cung cấp ngôn ngữ Java, JVM và những API nền tảng. **Java EE** trước đây là hệ công nghệ enterprise dựa trên nhiều đặc tả như Servlet, JPA, CDI, Bean Validation và JAX-RS. Các đặc tả enterprise được tiếp tục phát triển dưới tên **Jakarta EE**.

Hai bước migration thường có quan hệ nhưng phải được phân tích riêng:

- **Nâng JDK**: ví dụ Java 8 → Java 11 hoặc Java 17, ảnh hưởng runtime, module system, API bị loại bỏ, compiler và thư viện.
- **Đổi namespace enterprise API**: ví dụ Servlet/JPA từ `javax.*` sang `jakarta.*`, ảnh hưởng source, binary interface, descriptor và runtime container.

Một ứng dụng có thể chạy trên JDK mới với một số thư viện dùng `javax.*` nếu stack được chọn vẫn hỗ trợ. Ngược lại, đổi tất cả source sang `jakarta.*` không bảo đảm ứng dụng chạy được khi application server hoặc framework còn sử dụng API `javax.*`.

### 1.2. Jakarta EE 8 khác Jakarta EE 9

Đây là điểm dễ nhầm lẫn nhất:

| Dòng nền tảng | Namespace enterprise chủ yếu | Hệ quả migration |
| --- | --- | --- |
| Java EE 8 | `javax.*` | API enterprise mang namespace cũ. |
| Jakarta EE 8 | Vẫn là `javax.*` | Tên thương hiệu thay đổi nhưng chưa chuyển đồng loạt package sang `jakarta.*`. |
| Jakarta EE 9 / 9.1 | Nhiều API enterprise đổi sang `jakarta.*` | Đây là mốc thay đổi namespace quan trọng đối với Servlet, Persistence, CDI, Validation... |
| Jakarta EE 10 và các dòng sau | `jakarta.*` với các thay đổi API mới theo từng đặc tả | Ngoài đổi namespace, còn phải kiểm tra khác biệt behavior, API và baseline Java. |

**Không dùng tên “Jakarta” của một dependency làm bằng chứng package đã đổi.** Ví dụ một API có groupId `jakarta.*` nhưng phiên bản cũ vẫn xuất class `javax.*`. Luôn xem **nội dung JAR, artifact version và API mà framework/container thực sự cung cấp**.

### 1.3. Binary compatibility bị phá khi package đổi

Ở mức JVM, tên package là một phần của tên kiểu và method descriptor:

~~~text
Trước:
  javax.servlet.http.HttpServletRequest

Sau:
  jakarta.servlet.http.HttpServletRequest
~~~

Đây là **hai kiểu khác nhau**, không phải alias. Ví dụ method:

~~~java
void handle(javax.servlet.http.HttpServletRequest request);
~~~

khác descriptor với:

~~~java
void handle(jakarta.servlet.http.HttpServletRequest request);
~~~

Vì vậy một thư viện được biên dịch dùng `javax.servlet.*` không tự trở thành tương thích với servlet container cung cấp `jakarta.servlet.*` chỉ vì tên class đơn giản vẫn là `HttpServletRequest`. Có thể cần phiên bản thư viện mới, recompilation hoặc adapter được thiết kế rõ ràng.

## 2. Lập bản đồ chuyển đổi trước khi sửa source

Không nên chọn “Replace All” cho toàn repository ngay từ đầu. Trước hết phân loại từng namespace đang xuất hiện.

### 2.1. Những mapping enterprise API thường gặp

| API / đặc tả | Tên cũ | Tên mới thường gặp | Ghi chú |
| --- | --- | --- | --- |
| Servlet | `javax.servlet.*` | `jakarta.servlet.*` | Bao gồm servlet, filter, listener và HTTP APIs. |
| JavaServer Pages / Jakarta Server Pages | `javax.servlet.jsp.*` | `jakarta.servlet.jsp.*` | Kiểm tra JSP engine và JSTL/taglib tương thích. |
| JPA / Jakarta Persistence | `javax.persistence.*` | `jakarta.persistence.*` | Cập nhật entity annotations, interfaces, XML và provider. |
| Bean Validation | `javax.validation.*` | `jakarta.validation.*` | Ví dụ `@Valid`, `@NotNull`, `Validator`. |
| CDI | `javax.enterprise.*` | `jakarta.enterprise.*` | Contexts, scopes, events, interceptor bindings. |
| Injection | `javax.inject.*` | `jakarta.inject.*` | Ví dụ `@Inject`, `@Named`, `Provider`. |
| Common annotations | `javax.annotation.*` | `jakarta.annotation.*` | Ví dụ `@PostConstruct`, `@PreDestroy`; không áp dụng cho tất cả Java SE annotation packages. |
| JAX-RS / REST | `javax.ws.rs.*` | `jakarta.ws.rs.*` | `@Path`, `@GET`, `Response`, filters/providers. |
| JAX-WS | `javax.xml.ws.*` | `jakarta.xml.ws.*` | Chú ý source generation và SOAP tooling. |
| JAXB / XML Binding | `javax.xml.bind.*` | `jakarta.xml.bind.*` | Annotation, runtime, XJC/generated class. |
| JSON-B | `javax.json.bind.*` | `jakarta.json.bind.*` | Cần JSON-B implementation tương thích. |
| JSON-P | `javax.json.*` | `jakarta.json.*` | Không nhầm với JSON libraries bên thứ ba. |
| Jakarta Messaging (JMS) | `javax.jms.*` | `jakarta.jms.*` | Client, broker adapter và JMS provider. |
| Mail | `javax.mail.*` | `jakarta.mail.*` | Xem cả Jakarta Activation. |
| Activation | `javax.activation.*` | `jakarta.activation.*` | Kiểm tra runtime/provider. |
| Jakarta Transactions | `javax.transaction.*` | `jakarta.transaction.*` | Cẩn trọng ngoại lệ `javax.transaction.xa.*` là Java SE API. |
| Expression Language | `javax.el.*` | `jakarta.el.*` | Ảnh hưởng JSP/JSF/validation integration. |
| Faces (JSF) | `javax.faces.*` | `jakarta.faces.*` | Gồm annotation, taglib, faces-config. |
| EJB / Enterprise Beans | `javax.ejb.*` | `jakarta.ejb.*` | Kiểm tra container và deployment descriptor. |
| WebSocket | `javax.websocket.*` | `jakarta.websocket.*` | Client/server endpoint và annotation. |
| Security enterprise | `javax.security.enterprise.*` | `jakarta.security.enterprise.*` | Khác với Java SE security packages. |
| Servlet authentication | `javax.security.auth.message.*` | `jakarta.security.auth.message.*` | Kiểm tra runtime/container hỗ trợ. |

Đây là bản đồ định hướng; **phạm vi thực tế phải theo phiên bản đặc tả và dependency được chọn**. Không có một phép biến đổi áp dụng hợp lệ cho toàn bộ package `javax`.

### 2.2. Những package `javax.*` không được đổi máy móc

Một số package vẫn là API thuộc Java SE, ví dụ:

~~~java
import javax.crypto.Cipher;
import javax.net.ssl.SSLContext;
import javax.sql.DataSource;
import javax.naming.InitialContext;
import javax.management.MBeanServer;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.transform.Transformer;
import javax.xml.namespace.QName;
import javax.annotation.processing.Generated;
~~~

Các package trên **không trở thành `jakarta.crypto`, `jakarta.sql` hay `jakarta.xml.parsers`**. Việc rename mù quáng sẽ tạo import không tồn tại và phá source.

Đặc biệt:

- `javax.sql.DataSource` vẫn là interface Java SE dù ứng dụng dùng nó qua JPA hoặc Jakarta Transactions.
- `javax.naming.InitialContext` vẫn thường được dùng cho JNDI lookup.
- `javax.transaction.xa.XAResource` thuộc Java SE; không suy ra phải đổi cùng `javax.transaction.UserTransaction`.
- `javax.xml.*` có cả Java SE XML APIs và các API enterprise đã tách; cần xác định từng subpackage.
- `javax.annotation.processing.Generated` của compiler khác với một số annotation enterprise lifecycle như `jakarta.annotation.PostConstruct`.

**Nguyên tắc:** trước khi rename, tra groupId/artifact, class owner, module và Java baseline của API đó.

## 3. Kiểm kê chỗ sử dụng namespace cũ

### 3.1. Không chỉ tìm `import`

Một repository có thể chứa tên `javax.servlet` trong:

- Java/Kotlin/Groovy source.
- Java annotation ở code ứng dụng và test.
- Generated source do OpenAPI, JAXB, JPA metamodel hoặc framework tạo.
- `web.xml`, `persistence.xml`, `beans.xml`, `orm.xml`, `faces-config.xml`, `validation.xml`.
- `application.properties`, `application.yml`, Spring XML.
- `META-INF/services/*`.
- Manifest hoặc framework resource metadata.
- Build files, plugin configuration, code generation templates.
- String literal `Class.forName(...)`.
- Database, parameter store, environment variable hoặc config server ngoài repository.
- Serialization data hoặc metadata type name tồn tại qua nhiều release.

Vì thế tiêu chí khảo sát là **mọi nơi có chứa contract type name hoặc XML namespace**, không phải chỉ số lượng file `.java` được đổi.

### 3.2. Gợi ý lệnh tìm kiếm trong repository

Tìm namespace enterprise cũ:

~~~bash
rg -n 'javax\.(servlet|persistence|validation|enterprise|inject|annotation|ws\.rs|xml\.bind|xml\.ws|jms|mail|activation|faces|ejb|websocket)' .
~~~

Tìm XML schema và namespace legacy:

~~~bash
rg -n 'java\.sun\.com/xml/ns/javaee|xmlns\.jcp\.org/xml/ns/javaee|xmlns\.jcp\.org/xml/ns/persistence|web-app_[0-9]|persistence_[0-9]|beans_[0-9]' .
~~~

Tìm cơ chế nạp động và provider:

~~~bash
rg -n 'Class\.forName|loadClass|ServiceLoader|PersistenceProvider|provider\.class|listener-class|filter-class|servlet-class' .
~~~

Tìm file và thư mục metadata:

~~~bash
rg --files | rg '(web\.xml|persistence\.xml|orm\.xml|beans\.xml|faces-config\.xml|validation\.xml|META-INF/services|spring\.factories|application\.(yml|yaml|properties))'
~~~

Các lệnh là **điểm khởi đầu**, không thể phát hiện mọi dữ liệu trong JAR nhị phân, nguồn cấu hình bên ngoài hoặc thư viện do container cung cấp.

### 3.3. Bảng kiểm kê trước khi sửa

| Thành phần | Vị trí | API/namespace hiện tại | Đích dự kiến | Chủ sở hữu | Rủi ro |
| --- | --- | --- | --- | --- | --- |
| Servlet | `src/main/java` | `javax.servlet` | `jakarta.servlet` | Web team | Container tương thích. |
| JPA | Entity + `persistence.xml` | `javax.persistence` | `jakarta.persistence` | Data team | Provider, ORM schema. |
| CDI | Source + `beans.xml` | `javax.enterprise` | `jakarta.enterprise` | Backend | Discovery/interceptor. |
| REST | Source + config | `javax.ws.rs` | `jakarta.ws.rs` | API team | Servlet/JAX-RS runtime. |
| SPI | `META-INF/services` | Tên interface/provider cũ | Tên đúng theo API mới | Platform | Provider không tìm thấy. |
| Config ngoài | Config server/DB | FQCN đang sử dụng | Tên class runtime thực tế | Operations | Deploy lệch phiên bản. |

Đối với mỗi thay đổi, giữ bằng chứng về dependency và runtime target. Tránh ghi một mapping chỉ dựa vào tên package mà chưa biết thành phần nào chịu trách nhiệm.

## 4. Sửa import Java có chọn lọc

### 4.1. Servlet: ví dụ trước và sau

**Trước – Java EE / Jakarta EE 8:**

~~~java
package com.example.web;

import java.io.IOException;
import javax.servlet.ServletException;
import javax.servlet.annotation.WebServlet;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

@WebServlet("/health")
public class HealthServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response)
            throws ServletException, IOException {
        response.getWriter().write("OK");
    }
}
~~~

**Sau – namespace Jakarta Servlet:**

~~~java
package com.example.web;

import java.io.IOException;
import jakarta.servlet.ServletException;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

@WebServlet("/health")
public class HealthServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response)
            throws ServletException, IOException {
        response.getWriter().write("OK");
    }
}
~~~

Ở đây `java.io.IOException` **giữ nguyên**; package ứng dụng `com.example.web` cũng không cần đổi. Phần bắt buộc là import và binary types do Servlet API cung cấp. Sau khi sửa phải deploy trên container tương thích Jakarta Servlet tương ứng.

### 4.2. REST/JAX-RS

Trước:

~~~java
import javax.ws.rs.GET;
import javax.ws.rs.Path;
import javax.ws.rs.core.Response;
~~~

Sau:

~~~java
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.core.Response;
~~~

Ví dụ:

~~~java
@Path("/status")
public class StatusResource {
    @GET
    public Response status() {
        return Response.ok("ready").build();
    }
}
~~~

Source có thể trông không đổi ngoài import, nhưng runtime JAX-RS implementation, servlet integration và provider metadata phải thuộc **cùng thế hệ Jakarta**. Một interface `javax.ws.rs.ext.MessageBodyReader` không thể tự đăng ký như `jakarta.ws.rs.ext.MessageBodyReader`.

### 4.3. JPA và Bean Validation

Trước:

~~~java
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.validation.constraints.NotNull;
~~~

Sau:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.validation.constraints.NotNull;
~~~

Ví dụ:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.validation.constraints.NotNull;

@Entity
public class Customer {
    @Id
    private Long id;

    @NotNull
    private String name;
}
~~~

Khi chuyển đổi, phải đồng bộ entity annotations với phiên bản JPA provider và Bean Validation provider. Chỉ có `jakarta.persistence-api` mà thiếu implementation thích hợp không giúp ứng dụng tự tạo `EntityManagerFactory`.

### 4.4. Generated source và mã nguồn được sinh lại

Một dự án có thể sinh code mỗi lần build, ví dụ:

- JAXB từ XSD/WSDL.
- JAX-WS SOAP client.
- JPA static metamodel.
- OpenAPI server/client.
- Annotation processing và framework codegen.
- Mẫu source từ internal scaffolding.

Nếu generated file còn `javax.xml.bind.annotation.XmlElement`, không nên sửa tay rồi đợi lần build sau ghi đè. Hãy cập nhật **generator/plugin version, template và runtime API**, sau đó sinh lại source đúng Jakarta namespace.

Với một số generator, namespace của code sinh không chỉ phụ thuộc JDK, mà còn phụ thuộc version plugin và option mà generator hỗ trợ. Ghi lại kết quả generated API như một phần của migration.

## 5. Annotation: đổi type không đồng nghĩa giữ nguyên toàn bộ contract

### 5.1. Annotation cùng simple name nhưng khác runtime type

Ví dụ:

~~~java
@javax.persistence.Entity
~~~

và:

~~~java
@jakarta.persistence.Entity
~~~

là **hai annotation type khác nhau**. Framework scan annotation bằng class type có thể chỉ nhận loại tương ứng với implementation đang dùng.

Nếu một entity được gắn annotation cũ trong khi JPA provider mới chỉ xử lý Jakarta Persistence, entity có thể không được nhận diện. Hậu quả không nhất thiết là lỗi compile; có thể xuất hiện tại startup dưới dạng lỗi mapping hoặc khi truy cập repository.

### 5.2. CDI và injection

Trước:

~~~java
import javax.enterprise.context.ApplicationScoped;
import javax.inject.Inject;
~~~

Sau:

~~~java
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
~~~

Ví dụ:

~~~java
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;

@ApplicationScoped
public class OrderService {
    @Inject
    OrderRepository repository;
}
~~~

Không chỉ source cần đổi: CDI container, extension, interceptor và bean discovery configuration cũng phải tương thích. Một CDI extension cũ sử dụng `javax.enterprise.inject.spi.Extension` không tự hoạt động với runtime chờ `jakarta.enterprise.inject.spi.Extension`.

### 5.3. Lifecycle annotations

Các annotation thường gặp:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

public class StartupBean {
    @PostConstruct
    void initialize() {
        // Khởi tạo tài nguyên.
    }

    @PreDestroy
    void shutdown() {
        // Giải phóng tài nguyên.
    }
}
~~~

Khi đổi import, cần xác nhận container thực sự quản lý lifecycle của object. Đặt `@PostConstruct` trên một object tự tạo bằng `new` không tự đảm bảo framework sẽ gọi method đó.

### 5.4. `@Resource`, `@PersistenceContext` và tên JNDI

Ví dụ:

~~~java
import jakarta.annotation.Resource;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.EntityManager;

public class OrderRepository {
    @PersistenceContext(unitName = "ordersPU")
    private EntityManager em;

    @Resource(lookup = "java:comp/env/jdbc/Orders")
    private javax.sql.DataSource dataSource;
}
~~~

Ở đây `@Resource` và `@PersistenceContext` thuộc Jakarta enterprise APIs, nhưng `DataSource` vẫn là `javax.sql.DataSource` của Java SE. Tên JNDI `java:comp/env/jdbc/Orders` là **tên tài nguyên cấu hình**, không phải Java package, nên không được đổi thành `jakarta:...` theo phép tìm-thay.

### 5.5. Annotation ở test và framework integration

Cần rà soát:

- Test fixture có `@RunWith`, extension hoặc annotation provider thuộc hệ cũ.
- Custom validation annotation dùng `ConstraintValidator` cũ.
- Interceptor annotation do CDI cũ cung cấp.
- JAXB annotations trên DTO được framework serialize.
- Auto-configuration hoặc annotation processing phụ thuộc vào metadata framework.

Đôi khi annotation có cùng tên và thuộc tính gần giống, nhưng module chứa nó và các service provider sử dụng nó đã khác. Compile thành công chưa chứng minh injection, validation hoặc lifecycle thực thi đúng.

## 6. XML descriptor: phải đổi namespace, XSD, version và nội dung

XML descriptor thường có **ba lớp khác nhau**:

1. **Tên phần tử/thuộc tính XML** theo schema.
2. **Namespace URI, schema location và version**.
3. **Giá trị chứa class name, provider name, resource name hoặc tên cấu hình**.

Thay mỗi `javax.` trong XML không đủ. Namespace XML không phải Java package, và XSD version cần khớp với Jakarta spec target.

### 6.1. Ví dụ `web.xml` trước migration

Ví dụ web descriptor từ thế hệ Java EE cũ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="http://xmlns.jcp.org/xml/ns/javaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://xmlns.jcp.org/xml/ns/javaee
           http://xmlns.jcp.org/xml/ns/javaee/web-app_4_0.xsd"
         version="4.0">

    <filter>
        <filter-name>traceFilter</filter-name>
        <filter-class>com.example.web.TraceFilter</filter-class>
    </filter>

    <filter-mapping>
        <filter-name>traceFilter</filter-name>
        <url-pattern>/*</url-pattern>
    </filter-mapping>
</web-app>
~~~

Giá trị `filter-class` là tên **class ứng dụng**. Nếu package ứng dụng không đổi, nó có thể giữ nguyên sau migration, dù chính class đó phải implement `jakarta.servlet.Filter`.

### 6.2. Ví dụ `web.xml` theo Jakarta Servlet 6.0

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           https://jakarta.ee/xml/ns/jakartaee
           https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
         version="6.0">

    <filter>
        <filter-name>traceFilter</filter-name>
        <filter-class>com.example.web.TraceFilter</filter-class>
    </filter>

    <filter-mapping>
        <filter-name>traceFilter</filter-name>
        <url-pattern>/*</url-pattern>
    </filter-mapping>
</web-app>
~~~

Ví dụ này phù hợp với **Jakarta Servlet 6.0**. Nếu runtime target là Jakarta Servlet 5.0, phải dùng descriptor version/schema tương ứng, không copy `version="6.0"` chỉ vì ứng dụng đã đổi namespace.

Những điểm cần nhớ:

- Đổi namespace URI sang namespace Jakarta của spec tương ứng.
- Đổi `xsi:schemaLocation` sang đúng URL XSD.
- Đổi `version` theo version Servlet mà container hỗ trợ.
- Kiểm tra element/attribute có thay đổi giữa các phiên bản spec không.
- Giữ tên `com.example.web.TraceFilter` nếu class ứng dụng không đổi FQCN.
- Kiểm tra `servlet-class`, `listener-class`, `filter-class`, error page và các entry class khác.

### 6.3. Annotation và `web.xml` phải nhất quán

Nếu một filter được khai báo bằng XML, class thực tế phải triển khai interface `jakarta.servlet.Filter` khi deploy vào container Jakarta Servlet. Nếu class chỉ thay `web.xml` mà vẫn implement `javax.servlet.Filter`, runtime có thể không xem đó là đúng kiểu filter.

Ngược lại, nếu container cho phép annotation scanning, cần xác nhận `@jakarta.servlet.annotation.WebFilter` và các cấu hình discovery thực tế được xử lý. Một ứng dụng có thể sử dụng annotation, descriptor hoặc kết hợp cả hai; phải kiểm tra hiệu lực và quy tắc precedence của container/spec đang dùng.

## 7. `persistence.xml` và `orm.xml`: JPA không chỉ là import entity

### 7.1. Descriptor Persistence cũ

Ví dụ theo Java Persistence 2.2:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
  xmlns="http://xmlns.jcp.org/xml/ns/persistence"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="
    http://xmlns.jcp.org/xml/ns/persistence
    http://xmlns.jcp.org/xml/ns/persistence/persistence_2_2.xsd"
  version="2.2">

    <persistence-unit name="ordersPU">
        <provider>org.example.jpa.LegacyProvider</provider>
        <class>com.example.model.Customer</class>
    </persistence-unit>
</persistence>
~~~

Tên `org.example.jpa.LegacyProvider` là minh họa cho provider class do runtime cụ thể cung cấp. Khi nâng lên Jakarta, tên này phải xác định theo **implementation và phiên bản provider thật**, không được tự thay bằng một tên suy đoán.

### 7.2. Descriptor Jakarta Persistence 3.0

Ví dụ theo Jakarta Persistence 3.0:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
  xmlns="https://jakarta.ee/xml/ns/persistence"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="
    https://jakarta.ee/xml/ns/persistence
    https://jakarta.ee/xml/ns/persistence/persistence_3_0.xsd"
  version="3.0">

    <persistence-unit name="ordersPU">
        <class>com.example.model.Customer</class>
        <properties>
            <property name="jakarta.persistence.schema-generation.database.action"
                      value="none"/>
        </properties>
    </persistence-unit>
</persistence>
~~~

Với phiên bản Persistence mới hơn, chọn đúng XSD và version tương ứng. Trong ví dụ, đã bỏ phần `<provider>` để tránh buộc người đọc vào một implementation giả định; container/runtime phải có provider hỗ trợ Jakarta Persistence.

Các việc cần xem xét:

- Tên unit `ordersPU` có giữ nguyên theo contract không?
- `<class>` có chứa FQCN ứng dụng được đổi package không?
- `<mapping-file>` có trỏ đúng `orm.xml` mới không?
- Các thuộc tính chuẩn có đổi từ prefix `javax.persistence.*` sang `jakarta.persistence.*` không?
- Các thuộc tính vendor-specific có giữ nguyên tên/hành vi theo version provider không?
- JDBC datasource JNDI name và `javax.sql.DataSource` có phải giữ nguyên không?
- Provider đang dùng Jakarta Persistence version nào?

Không tự bật `schema-generation.database.action=drop-and-create` trong migration production. Thay namespace và thay schema database là hai thay đổi cần kiểm soát độc lập.

### 7.3. `orm.xml` và metadata mapping

Ngoài annotation, Hibernate/EclipseLink hoặc JPA provider có thể sử dụng XML mapping. Một entity không có annotation vẫn có thể được ánh xạ trong `orm.xml`.

Vì vậy, audit cần tìm:

- XML namespace và XSD version của mapping file.
- FQCN entity/embeddable/converter/listener bên trong XML.
- Các tên property hoặc type tương ứng provider.
- Package mà mapping file áp dụng.
- Các converter hoặc callback class có namespace Java cũ không.

Một migration chỉ thay `@Entity` nhưng bỏ qua `orm.xml` có thể chạy một phần và lỗi ở entity khác khi khởi tạo persistence unit.

### 7.4. Cấu hình JPA trong application properties

Ví dụ khóa chuẩn JDBC trong persistence config có thể chuyển:

~~~properties
# Thế hệ Jakarta Persistence
jakarta.persistence.jdbc.url=jdbc:postgresql://localhost:5432/orders
jakarta.persistence.jdbc.user=app_user
jakarta.persistence.jdbc.password=example-placeholder
~~~

Trong thực tế, đừng đưa credential thật vào file ví dụ hoặc version control; dùng secret manager/biến môi trường.

Quan trọng: không phải mọi khóa chứa chuỗi `javax.persistence` hoặc `hibernate` có cùng quy tắc rename. Các khóa chuẩn của đặc tả và các khóa cấu hình riêng của provider/framework cần được kiểm tra riêng.

## 8. `beans.xml`, CDI, Validation và Faces descriptors

### 8.1. CDI: `beans.xml`

Trong Jakarta CDI, `beans.xml` có thể chứa namespace và version mới, cùng cấu hình bean discovery và interceptors.

Ví dụ minh họa theo CDI 4.0:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="https://jakarta.ee/xml/ns/jakartaee"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
         https://jakarta.ee/xml/ns/jakartaee
         https://jakarta.ee/xml/ns/jakartaee/beans_4_0.xsd"
       bean-discovery-mode="annotated"
       version="4.0">
</beans>
~~~

Không chỉ đổi schema. **Quy tắc discovery có thể thay đổi giữa phiên bản CDI**. Với `bean-discovery-mode="annotated"`, các bean không mang bean-defining annotation phù hợp có thể không được phát hiện. Migration phải kiểm tra dependency injection thực tế.

### 8.2. Bean Validation: `validation.xml`

Các framework có thể đọc `META-INF/validation.xml` để cấu hình message interpolator, validator factory, constraint mapping và provider. Khi nâng sang Jakarta Validation, kiểm tra:

- Namespace và schema của phiên bản Validation đích.
- Class name của `ConstraintValidatorFactory`, `MessageInterpolator` và provider.
- Các XML constraint mapping bên ngoài annotation.
- Mã custom constraint còn implement `javax.validation.ConstraintValidator` hay đã chuyển sang `jakarta.validation.ConstraintValidator`.
- Runtime provider version có hỗ trợ namespace mới hay không.

Đừng chỉ đổi `@NotNull`; nếu custom validator và XML mapping chưa đổi, quá trình khởi tạo validation có thể hỏng.

### 8.3. Jakarta Faces: `faces-config.xml` và tag libraries

Nếu ứng dụng dùng JSF/Jakarta Faces, phạm vi migration có thể gồm:

- Import `javax.faces.*` → `jakarta.faces.*`.
- `faces-config.xml` namespace/XSD/version.
- Managed bean, converter, validator, phase listener trong XML.
- Expression Language và phụ thuộc `javax.el.*` → `jakarta.el.*` khi dùng thế hệ tương ứng.
- Facelets taglib URI hoặc tag library của framework.
- Component libraries (ví dụ UI widgets) phải hỗ trợ version Jakarta Faces đích.

Một file XHTML có thể không chứa `javax.` nhưng vẫn sử dụng tag library URI cũ hoặc namespace do thư viện UI công bố. Những URI này phải được thay theo **tài liệu của thư viện và đặc tả target**, không thay mù mọi `java.sun.com` hoặc `xmlns.jcp.org` xuất hiện trong tài liệu HTML/XML bất kỳ.

## 9. Tên class trong XML và cấu hình ứng dụng

### 9.1. Phân biệt tên class ứng dụng với tên API framework

Ví dụ `web.xml` chứa:

~~~xml
<servlet-class>com.example.web.CustomerServlet</servlet-class>
~~~

Nếu chỉ đổi import của `CustomerServlet` từ `javax.servlet` sang `jakarta.servlet` nhưng vẫn giữ package `com.example.web`, **giá trị này không cần đổi**.

Ngược lại, nếu descriptor chứa một implementation class của thư viện có package đã đổi:

~~~xml
<listener-class>com.vendor.legacy.LegacyListener</listener-class>
~~~

thì phải xác định **class replacement thực tế** của phiên bản thư viện Jakarta. Không có quy tắc chung rằng mọi `com.vendor.legacy` biến thành một tên có chữ `jakarta`.

### 9.2. Cấu hình Spring hoặc framework khác

Một cấu hình có thể chứa FQCN:

~~~yaml
application:
  converter-class: com.example.legacy.LegacyConverter
  security-filter-class: com.vendor.security.LegacyFilter
~~~

Nếu source Java hoặc dependency thay class name, cần cập nhật value tương ứng. Nhưng nhiều property framework như `spring.jpa.*`, `server.servlet.*` hoặc key do chính ứng dụng định nghĩa **không được đổi prefix chỉ vì Jakarta EE**.

Điều đúng là kiểm tra contract của phiên bản framework:

- Property name còn hợp lệ không?
- Value là class name, bean name, resource path hay identifier nghiệp vụ?
- Class mới thuộc package nào?
- Framework có cơ chế binding/configuration riêng hoặc adapter không?
- Cấu hình này được đọc trong profile nào?

### 9.3. Reflection dùng `Class.forName` hoặc `loadClass`

Ví dụ:

~~~java
String name = config.getProperty("handler.class");
Class<?> handlerType = Class.forName(name);
~~~

Nếu `handler.class` nằm trong file bên ngoài JAR hoặc database, công cụ sửa source không thể tự thay. Lúc chạy có thể xuất hiện `ClassNotFoundException`.

Khi điều tra, ghi:

1. Value thực tế của cấu hình trong môi trường bị lỗi.
2. Class name có tồn tại trong JAR của version mới không.
3. Class loader/module layer đang dùng để nạp.
4. Constructor và interface mà framework mong đợi.
5. Có dependency `javax.*` còn tồn tại trong chữ ký class mới không.

Có khi tên đã đúng nhưng class implement interface cũ, khiến lỗi chuyển từ `ClassNotFoundException` thành `ClassCastException`.

### 9.4. Đổi namespace ở dữ liệu tồn tại lâu dài

Tên class có thể được ghi vào JSON polymorphic type metadata, cache hoặc serialization. Ví dụ:

~~~json
{
  "type": "javax.example.LegacyHandler",
  "payload": {}
}
~~~

Đây chỉ là ví dụ minh họa cho một tên type lưu dạng chuỗi, không phải một mapping API Jakarta chuẩn. Nếu dữ liệu cũ dùng FQCN để chọn decoder, việc thay code mới có thể khiến dữ liệu lịch sử không còn đọc được.

Giải pháp có thể là xây **alias có whitelist**, DTO schema ổn định hoặc migration dữ liệu có backup. Không bật class loading tùy ý từ input không tin cậy chỉ để hỗ trợ tên cũ.

## 10. `META-INF/services` và provider metadata

### 10.1. Java ServiceLoader tìm provider như thế nào?

Một thư viện có thể đăng ký provider bằng file:

~~~text
META-INF/services/<fully-qualified-service-interface>
~~~

Nội dung là danh sách class implementation, ví dụ:

~~~text
com.example.provider.DefaultProvider
~~~

Khi **service interface** đổi namespace từ `javax.*` sang `jakarta.*`, **tên file metadata cũng có thể phải đổi**. Nếu provider class đổi package, **nội dung file** cũng phải đổi tương ứng.

### 10.2. Ví dụ Persistence provider

Một môi trường Jakarta Persistence có thể cần service descriptor đặt theo interface Jakarta:

~~~text
META-INF/services/jakarta.persistence.spi.PersistenceProvider
~~~

Nội dung file trỏ đến provider class mà phiên bản thư viện thực tế cung cấp. Không tự đặt tên provider dựa trên suy đoán; phải dùng metadata được provider chính thức phát hành.

Tương tự, một CDI extension có interface `jakarta.enterprise.inject.spi.Extension`, không phải interface `javax.enterprise.inject.spi.Extension`. Nếu file service vẫn mang tên cũ, runtime có thể không phát hiện extension.

### 10.3. Ảnh hưởng của shading và fat JAR

Nếu ứng dụng gộp nhiều JAR hoặc relocate dependency, `META-INF/services` có thể bị:

- Mất file khi resource có đường dẫn trùng.
- Giữ filename interface cũ trong khi class mới dùng `jakarta.*`.
- Giữ provider class name cũ.
- Trỏ đến class không còn nằm trong artifact.
- Gộp nhầm provider thuộc hai namespace không tương thích.

Không coi việc `Class.forName(provider)` thành công là bằng chứng `ServiceLoader` đã đăng ký provider đúng. Cần chạy luồng ServiceLoader/framework provider discovery thật.

### 10.4. JPMS `uses`/`provides`

Nếu ứng dụng chạy với explicit named modules, có thể có:

~~~java
module com.example.provider {
    requires jakarta.persistence;
    provides jakarta.persistence.spi.PersistenceProvider
        with com.example.provider.CustomPersistenceProvider;
}
~~~

Ví dụ chỉ hợp lệ nếu class provider thực sự implement đúng SPI và module dependencies phù hợp. Đối với implementation bên thứ ba, không nên tự viết descriptor thay thế khi chưa biết thiết kế nhà cung cấp.

Khi chuyển namespace, xác minh `module-info.java`/`module-info.class`, module name, package exports/opens và việc module provider được phân giải. File `META-INF/services` không phải cơ chế duy nhất trên module path.

## 11. Dependency và application server phải cùng hệ namespace

### 11.1. Không thể chỉ sửa import rồi giữ container cũ

Một servlet được biên dịch như:

~~~java
public final class HealthServlet
        extends jakarta.servlet.http.HttpServlet {
}
~~~

cần runtime/container cung cấp Jakarta Servlet API tương ứng. Một container chỉ hỗ trợ `javax.servlet.*` không tự nhận kiểu này.

Ngược lại, một ứng dụng `javax.servlet.*` cũ cũng không tự triển khai được lên container chỉ hỗ trợ `jakarta.servlet.*`, trừ khi có một cơ chế chuyển đổi/compatibility được nhà cung cấp hỗ trợ và đã được kiểm chứng.

### 11.2. Đọc ma trận framework/container trước khi đổi

Những cặp phiên bản thường gặp về mặt định hướng:

| Stack | Namespace chủ yếu | Điều cần xác minh |
| --- | --- | --- |
| Servlet container đời cũ (ví dụ dòng Servlet 4) | `javax.servlet.*` | Thường không phù hợp với WAR biên dịch cho `jakarta.servlet.*`. |
| Servlet container Jakarta Servlet 5+ | `jakarta.servlet.*` | Kiểm tra đúng Servlet level, JSP, WebSocket và JDK yêu cầu. |
| Spring Framework 5.x / Spring Boot 2.x | Chủ yếu tích hợp namespace enterprise `javax.*` | Cần kế hoạch nâng framework trước khi chuyển toàn bộ stack sang Jakarta. |
| Spring Framework 6.x / Spring Boot 3.x | Jakarta namespace cho các API enterprise liên quan | Kiểm tra JDK tối thiểu, dependency starter và thư viện tích hợp. |
| Hibernate ORM thế hệ trước Jakarta | JPA `javax.persistence.*` ở nhiều bản | Không trộn entity annotations Jakarta với provider chỉ hiểu javax. |
| Hibernate ORM thế hệ Jakarta (ví dụ 6.x) | Jakarta Persistence | Kiểm tra API behavior, dialect, query và mapping thay đổi ngoài namespace. |

Các dòng được nêu chỉ nhằm thể hiện quan hệ tương thích. Cần kiểm tra **phiên bản cụ thể mà sản phẩm chọn**, vì yêu cầu JDK và tính năng hỗ trợ thay đổi theo release.

### 11.3. Servlet API thường không nên đóng gói lặp trong WAR

Nếu WAR được triển khai trên application server, Servlet API thường do container cung cấp. Với Maven, dependency API có thể dùng `provided`:

~~~xml
<dependency>
  <groupId>jakarta.servlet</groupId>
  <artifactId>jakarta.servlet-api</artifactId>
  <version>6.0.0</version>
  <scope>provided</scope>
</dependency>
~~~

Ví dụ version phù hợp với Jakarta Servlet 6.0; không dùng nguyên si cho container chỉ hỗ trợ Servlet 5.0. Đối với executable application, cấu hình packaging/starter có thể khác.

Đừng đưa đồng thời một bản `javax.servlet-api` và `jakarta.servlet-api` vào `WEB-INF/lib` rồi kỳ vọng container tự chuyển đổi giữa hai hệ type.

### 11.4. API JAR không phải implementation

Có import `jakarta.persistence.EntityManager` không có nghĩa đã có JPA provider; có `jakarta.validation.Validator` không có nghĩa đã có Bean Validation provider.

Một project cần xác định:

- API artifact của spec đúng version.
- Runtime provider hoặc container cung cấp implementation.
- Extension và SPI tương thích cùng namespace.
- Đúng scope ở compile, test và deploy.
- Không có bản API cũ từ dependency bắc cầu được chọn sai.

Với một server Jakarta EE đầy đủ, nhiều API/implementation do server cung cấp; đối với standalone app, cần khai báo runtime provider theo stack thực tế.

## 12. Lỗi khó phát hiện do API cũ và mới tồn tại song song

### 12.1. Hai annotation có cùng simple name

Một dự án có thể compile đồng thời:

~~~java
import javax.persistence.Entity;
~~~

và:

~~~java
import jakarta.persistence.Entity;
~~~

nếu cả hai API JAR có mặt. Nhưng việc compile không chứng minh runtime sẽ xử lý cả hai. Provider mới có thể chỉ scan annotation Jakarta, làm entity cũ không được quản lý.

Tình trạng này thường nguy hiểm hơn lỗi compile vì application có thể khởi động trong một số profile và lỗi trong profile khác.

### 12.2. Servlet filter/listener không cùng interface

Một filter cũ:

~~~java
public class LegacyFilter implements javax.servlet.Filter {
    // ...
}
~~~

không phải subtype của `jakarta.servlet.Filter`. Nếu container Jakarta cố cài đặt qua `web.xml` hoặc annotation, nó có thể báo incompatibility, class cast hoặc lỗi startup.

Không thể sửa chỉ bằng cách đổi XML schema nếu class chưa được biên dịch với API mới.

### 12.3. Các thư viện integration chưa theo kịp

Một thư viện REST client, security filter, JSP tag library, metrics integration hoặc custom JPA provider có thể vẫn phụ thuộc `javax.*`. Khi sửa ứng dụng, dependency cũ chưa chắc tương thích.

Cần phân loại dependency thành:

- Có phiên bản Jakarta chính thức.
- Có giải pháp thay thế được hỗ trợ.
- Có công cụ chuyển đổi bytecode/resource được vendor khuyến nghị.
- Phải cô lập sau ranh giới process hoặc giữ trên stack cũ trong giai đoạn chuyển tiếp.

Tránh tự tạo một JAR “bridge” chứa hai hệ API mà không có thiết kế adapter và test cụ thể.

## 13. XML namespace không phải chuỗi có thể thay hàng loạt

### 13.1. Bốn loại chuỗi dễ nhầm

Trong một XML file có thể đồng thời có:

~~~xml
xmlns="https://jakarta.ee/xml/ns/jakartaee"
xsi:schemaLocation="https://jakarta.ee/xml/ns/jakartaee ..."
<listener-class>com.example.web.SessionListener</listener-class>
<res-ref-name>jdbc/Orders</res-ref-name>
~~~

Ý nghĩa lần lượt:

1. **Namespace URI** xác định vocab/schema XML.
2. **Schema location** tham chiếu XSD tương ứng version.
3. **Class name** được framework/container nạp bằng reflection.
4. **Resource identifier** như JNDI name; không phải Java package.

Nếu dùng một phép thay chuỗi duy nhất để biến tất cả thành `jakarta.*`, kết quả có thể sai nặng.

### 13.2. Phiên bản schema phải gắn với runtime target

Một ứng dụng deploy Servlet 5.0 không nên dùng web descriptor version 6.0 chỉ vì muốn “mới nhất”. Ngược lại, giữ descriptor namespace cũ có thể khiến container Jakarta mới xử lý theo cơ chế tương thích riêng hoặc từ chối.

Lựa chọn đúng là:

- Chọn stack và spec versions mục tiêu.
- Lấy XML schema tương ứng.
- Sửa namespace/schema/version theo đặc tả.
- Kiểm tra nội dung class name và element được hỗ trợ.
- Deploy và xác minh descriptor đã được parser nhận.

### 13.3. XML validation không thay thế runtime test

Một descriptor hợp lệ với XSD chưa chắc:

- Class `filter-class` tồn tại.
- Class implements đúng `jakarta.servlet.Filter`.
- Persistence provider tương thích.
- CDI bean thực sự được phát hiện.
- JNDI resource có trong server.
- Listener hoặc extension được khởi tạo thành công.

XML validation giúp phát hiện lỗi cấu trúc; test runtime cần kiểm tra wiring và type compatibility.

## 14. Tự động hóa sửa mã: dùng có chọn lọc

### 14.1. Những việc công cụ có thể làm tốt

Các công cụ source refactoring như OpenRewrite hoặc chức năng migration của IDE có thể hỗ trợ:

- Đổi import enterprise API theo mapping được xác định.
- Đổi fully qualified type references trong source.
- Chỉnh một số annotation và API usages.
- Cập nhật dependency coordinates/versions theo recipe.
- Xử lý một số cấu hình và XML format mà recipe hỗ trợ.

Một số hệ sinh thái có công cụ transformer bytecode/resource để hỗ trợ đổi namespace khi thiếu source. Nhưng độ bao phủ và rủi ro phụ thuộc version công cụ, artifact và target.

Tự động hóa phù hợp nhất khi mapping có cấu trúc rõ ràng và có thể review diff.

### 14.2. Vì sao không chạy “thay `javax.` → `jakarta.`” toàn bộ?

Một lệnh replace như vậy có thể phá:

~~~java
javax.sql.DataSource
javax.crypto.Cipher
javax.naming.InitialContext
javax.xml.parsers.DocumentBuilderFactory
~~~

nên tuyệt đối không dùng như phương án mặc định. Chỉ thay đúng danh sách enterprise packages và tính đến trường hợp ngoại lệ. Ngay cả mapping theo prefix cũng phải xem API/đặc tả đích.

### 14.3. Cách quản lý thay đổi bằng nhiều commit nhỏ

Có thể chia thành các commit hoặc pull request theo phạm vi:

1. Khóa baseline và dependency versions.
2. Nâng framework/container và các thư viện tích hợp.
3. Đổi import/annotation trong source.
4. Cập nhật generated code source/templates.
5. Cập nhật XML namespace/XSD/version.
6. Cập nhật config class names và SPI metadata.
7. Cập nhật tests, test engine, fixtures và packaging.
8. Đánh giá runtime behavior và xóa dependency cũ.
9. Chốt tài liệu migration, cấu hình deploy và rollback.

Khi các nhóm thay đổi được tách rõ, dễ xác định lỗi do source, XML, SPI hay runtime stack.

## 15. Test migration: điều gì cần được xác nhận?

### 15.1. Compile cả source và test

Kiểm tra rằng:

- Không còn import `javax.*` enterprise ở những module phải chuyển hoàn toàn sang Jakarta.
- Không làm mất các Java SE `javax.*` hợp lệ.
- Test framework, mock và extension đã dùng API Jakarta phù hợp.
- Generated source không đưa namespace cũ trở lại.
- Không có class-path dependency được chọn sai version.

Sự vắng mặt của `javax.*` trong source chưa chứng minh artifact đã sạch vì JAR bên thứ ba có thể chứa bytecode hoặc metadata cũ.

### 15.2. Startup trên đúng application server

Triển khai ứng dụng trên server/runtime target và kiểm tra:

- Servlet/filter/listener được đăng ký.
- REST endpoints phản hồi.
- CDI injection hoạt động.
- JPA persistence unit khởi tạo và mapping entity đúng.
- Validation được kích hoạt.
- Security integration hoạt động.
- JSP/Faces/tag libraries render đúng nếu có.
- SOAP/JAXB/JMS/Mail modules hoạt động nếu thuộc scope.

Một phép smoke test chỉ gọi health endpoint có thể bỏ sót provider chỉ được dùng trong một tính năng hiếm.

### 15.3. Kiểm tra XML descriptors và metadata

Một bộ kiểm tra thực tế nên gồm:

- XML parse/validation theo schema của spec target.
- Runtime loading từng descriptor (`web.xml`, `persistence.xml`, `beans.xml`, v.v.).
- Danh sách class được cấu hình qua `servlet-class`, `filter-class`, `listener-class`, `provider`.
- Metadata `META-INF/services` và các resource khác trong JAR/WAR cuối.
- Test ServiceLoader hoặc provider discovery.
- Dependency tree và nội dung `WEB-INF/lib`.
- Config từ environment/profile/remote store.

### 15.4. Giữ baseline về hành vi

Với những tính năng quan trọng, so sánh trước/sau:

| Luồng | Bằng chứng kỳ vọng |
| --- | --- |
| HTTP servlet/filter | Status, headers, encoding, session và filter order. |
| REST API | Request/response JSON, validation, exception mapping. |
| JPA | Entity mapping, transaction, lazy loading, query và schema. |
| CDI | Injection, scope và lifecycle callbacks. |
| Bean Validation | Constraint violations và message. |
| Authentication | Login, role, filter chain và session. |
| Messaging | Producer/consumer, deserialization và ack behavior. |
| JSP/Faces | Taglibs, component binding và render output. |

Cần so sánh các luồng theo **contract nghiệp vụ**, không chỉ theo khả năng startup.

## 16. Lộ trình migration có kiểm soát

### Giai đoạn 1: Chọn mục tiêu và chốt ma trận hỗ trợ

Xác định:

- JDK mục tiêu và baseline source/bytecode.
- Jakarta EE platform/spec versions mục tiêu.
- Application server/servlet container version.
- Framework (Spring, Hibernate, Faces, REST implementation...) và integration libraries.
- Cách đóng gói: WAR, EAR, executable JAR, modular runtime.
- Phạm vi được phép thay đổi và phương án rollback.

Không nên chuyển namespace khi chưa biết runtime target hỗ trợ API nào.

### Giai đoạn 2: Kiểm kê nguồn và phụ thuộc

Tạo bảng `javax.*` theo từng nhóm enterprise hoặc Java SE. Truy vết artifact owner, dependency bắc cầu, generated source, descriptor, SPI và external configs.

Đánh dấu những thành phần không còn có phiên bản Jakarta tương thích để quyết định thay thế/cô lập.

### Giai đoạn 3: Nâng dependency và công cụ build

Chọn một **hệ phiên bản đồng bộ**; tránh để API mới nhưng provider cũ. Cập nhật build plugin, annotation processor, code generator và test tooling phù hợp JDK target.

Với thư viện bên thứ ba, ưu tiên bản chính thức hỗ trợ Jakarta. Chỉ dùng bytecode transformer như giải pháp cầu nối có phạm vi nếu đã kiểm chứng giới hạn của công cụ.

### Giai đoạn 4: Sửa source imports và annotations

Dùng mapping enterprise có chọn lọc. Xem diff để bảo đảm không đụng tới `javax.sql`, `javax.crypto`, `javax.naming` và các Java SE packages khác. Cập nhật custom constraints, interceptors, injection, SOAP/JAXB REST adapters theo stack mục tiêu.

### Giai đoạn 5: Sửa XML descriptors

Cập nhật namespace URI, schema location và version phù hợp. Duyệt từng class name, JNDI name, provider name và property trong `web.xml`, `persistence.xml`, `beans.xml`, `orm.xml`, `validation.xml`, `faces-config.xml`. Không biến đổi những identifier nghiệp vụ không liên quan.

### Giai đoạn 6: Sửa metadata và cấu hình runtime

Cập nhật `META-INF/services`, file config, package scans, class names trong environment và cấu hình ngoài artifact. Đồng bộ config release/deploy với binary mới để không có giai đoạn code mới đọc config cũ không tương thích.

### Giai đoạn 7: Kiểm thử ở môi trường giống production

Biên dịch, chạy unit/integration tests, deploy lên container target, kiểm tra artifact cuối. Xác minh các provider, reflection, entity mapping, REST endpoints và legacy clients.

### Giai đoạn 8: Triển khai từng phần và rollback

Nếu hệ thống có nhiều service, cân nhắc tách theo ranh giới HTTP/message/database thay vì cố để `javax.servlet` và `jakarta.servlet` trộn trong cùng một ứng dụng.

Giữ artifact/cấu hình cũ có thể triển khai lại, kiểm tra migration dữ liệu độc lập và dùng canary khi phù hợp.

## 17. Đọc lỗi migration theo nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| `package javax.servlet does not exist` | Compile đã chuyển dependency API nhưng source vẫn dùng import cũ. | Sửa import theo Servlet target hoặc đồng bộ stack. |
| `package jakarta.servlet does not exist` | Chưa có Jakarta Servlet API ở compile classpath hoặc version sai. | Kiểm tra dependency và scope. |
| `ClassNotFoundException: javax...` | XML/config/provider còn FQCN cũ hoặc JAR cũ thiếu. | Tìm tên class trong descriptor và runtime artifact. |
| `ClassCastException` với Servlet/Provider | Hai thế hệ interface `javax`/`jakarta` không tương thích. | So chữ ký class/interface và dependency tree. |
| Filter/listener không load | Class chưa implement đúng Jakarta interface hoặc descriptor sai. | Kiểm tra source, `web.xml` và container spec. |
| JPA entity không được nhận | Annotation cũ, provider cũ hoặc `persistence.xml`/mapping sai. | Kiểm tra package annotation, API/provider và metadata. |
| `PersistenceException` khi bootstrap | Persistence unit, provider, class hoặc property sai. | Đọc root cause, XML schema và JPA runtime. |
| CDI bean không được inject | CDI API/container/discovery hoặc `beans.xml` chưa đồng bộ. | Kiểm tra bean-defining annotations và logs. |
| `ValidationException` | API/provider mismatch hoặc constraint metadata cũ. | Kiểm tra `jakarta.validation` và provider. |
| XML descriptor bị từ chối | Namespace/XSD/version không được runtime hỗ trợ. | Đối chiếu với spec target, validate XML. |
| `ServiceConfigurationError` | Provider metadata thiếu/sai tên hoặc provider sai interface. | Mở `META-INF/services` và kiểm tra provider runtime. |
| Test pass nhưng deploy fail | Unit test không chạy trên application server target. | Bổ sung integration/deployment tests. |
| `NoSuchMethodError` | Thư viện được compile với API khác version runtime. | So `javap` và dependency classpath. |
| `NoClassDefFoundError` | Thiếu runtime dependency, class cũ không còn. | Kiểm tra artifact WAR/EAR và server libs. |
| Chỉ profile production bị lỗi | Config FQCN/descriptor/remote property chưa migrate. | So môi trường và config thực tế. |

Không nên sửa mọi lỗi bằng cách thêm cả hai bộ `javax.*` và `jakarta.*` API vào runtime. Điều đó có thể che lỗi compile nhưng không tạo ra adapter type an toàn.

## 18. Mini-lab: chuyển một WAR đơn giản

### 18.1. Hiện trạng

Ứng dụng có:

~~~text
src/main/java/com/example/web/OrderServlet.java
src/main/java/com/example/web/RequestAuditFilter.java
src/main/java/com/example/model/Order.java
src/main/resources/META-INF/persistence.xml
src/main/webapp/WEB-INF/web.xml
pom.xml
~~~

- Servlet và filter import `javax.servlet.*`.
- Entity import `javax.persistence.*`.
- `web.xml` dùng namespace Java EE cũ.
- `persistence.xml` dùng namespace JPA 2.x.
- Application server mới yêu cầu Jakarta Servlet và Jakarta Persistence tương ứng.

### 18.2. Nhiệm vụ

1. Chọn target Servlet/Persistence spec versions và server JDK.
2. Thay đúng import Servlet/JPA; giữ `java.io.*` và `javax.sql.DataSource` nếu có.
3. Cập nhật annotation `@WebServlet`, `@Entity`, `@PersistenceContext` theo namespace Jakarta.
4. Chuyển `web.xml` sang namespace/XSD/version target.
5. Chuyển `persistence.xml` sang namespace/XSD/version target, kiểm tra provider.
6. Duyệt lại `servlet-class` và `filter-class`; giữ nguyên FQCN ứng dụng nếu package chưa đổi.
7. Xác minh không còn metadata provider có interface `javax.persistence.spi.PersistenceProvider` trong phần runtime cần Jakarta.
8. Deploy WAR trên container phù hợp, gọi endpoint và thử transaction JPA.
9. Kiểm tra classpath, dependency scope và runtime logs.

### 18.3. Những kết quả không đủ để hoàn tất

- **Chỉ chạy `mvn package` thành công:** chưa chứng minh container đọc XML và load provider đúng.
- **Chỉ thay `import`:** chưa xác nhận descriptor, annotation scanner và provider.
- **Chỉ sửa `web.xml`:** chưa xác nhận Servlet class implement `jakarta.servlet.Servlet`.
- **Chỉ thay `javax.` bằng `jakarta.` ở mọi file:** có nguy cơ phá Java SE APIs như `javax.sql.DataSource`.
- **Chỉ khởi động thành công:** chưa kiểm chứng JPA, injection và các đường xử lý ít được gọi.

### 18.4. Tiêu chí hoàn tất mini-lab

Đầu ra phải có:

- Bản đồ source import/annotation đã đổi.
- XML descriptors phù hợp spec version target.
- Dependency tree nhất quán.
- WAR thực tế có đúng API/provider scope.
- Runtime logs xác nhận servlet/filter/JPA bootstrap.
- Test gọi endpoint và truy cập persistence thành công.
- Danh sách cấu hình còn tên lớp legacy nếu có cùng người chịu trách nhiệm xử lý.

## 19. Checklist thực hành cho Java EE → Jakarta

- [ ] Đã phân biệt nâng JDK với đổi namespace enterprise.
- [ ] Đã xác định target Jakarta EE/Servlet/Persistence/CDI/Validation versions và runtime hỗ trợ.
- [ ] Đã nhớ rằng Jakarta EE 8 vẫn dùng namespace `javax.*`.
- [ ] Đã lập mapping enterprise API có chọn lọc, không đổi toàn bộ `javax.*`.
- [ ] Đã giữ nguyên Java SE APIs như `javax.sql`, `javax.naming`, `javax.crypto` và `javax.xml.parsers`.
- [ ] Đã sửa import, FQCN và annotation trong source chính và test.
- [ ] Đã cập nhật code generator/template để không sinh lại `javax.*` cũ.
- [ ] Đã đổi XML namespace, schema location và version cho descriptor theo spec đích.
- [ ] Đã kiểm tra tên class nằm trong `web.xml`, `persistence.xml`, `orm.xml`, `beans.xml`, `validation.xml` và `faces-config.xml`.
- [ ] Đã phân biệt class name với JNDI name hoặc identifier nghiệp vụ.
- [ ] Đã kiểm tra các property chuẩn có prefix `javax.persistence.*` và cấu hình provider-specific.
- [ ] Đã kiểm tra Spring/framework metadata, YAML/properties, biến môi trường và config ngoài repository.
- [ ] Đã rà soát `META-INF/services` filename/provider class theo interface Jakarta thực tế.
- [ ] Đã bảo đảm application server, API JAR, provider và framework cùng thế hệ tương thích.
- [ ] Đã kiểm tra test runtime và container thực tế thay vì chỉ compiler.
- [ ] Đã kiểm tra class loading, annotation discovery, injection, persistence, REST/servlet và service providers.
- [ ] Đã xem xét ảnh hưởng đến serialized data, cache và dữ liệu chứa FQCN lâu dài.
- [ ] Đã chuẩn bị rollback và tài liệu mô tả mapping cũng như dependency còn chưa tương thích.

## 20. Kết luận

Chuyển từ Java EE sang Jakarta EE là **thay đổi hợp đồng kiểu và metadata xuyên suốt ứng dụng**, không chỉ là thao tác đổi `import javax.*` thành `import jakarta.*`. Những annotation trông giống nhau có runtime type khác nhau; XML descriptor cần đúng namespace, XSD và version; tên class trong cấu hình, SPI metadata và các nguồn bên ngoài cũng phải trỏ đến implementation có thật trong stack Jakarta mục tiêu.

Cách tiếp cận đáng tin cậy là **chốt phiên bản runtime trước, lập bản đồ namespace có chọn lọc, sửa source và XML theo từng lớp, đồng bộ provider/config, rồi kiểm chứng trên artifact được deploy thực tế**. Làm như vậy giúp tránh cả hai cực đoan: giữ sót namespace cũ khiến runtime không nhận diện, hoặc thay thế quá rộng khiến API Java SE và các định danh nghiệp vụ hợp lệ bị phá vỡ.
