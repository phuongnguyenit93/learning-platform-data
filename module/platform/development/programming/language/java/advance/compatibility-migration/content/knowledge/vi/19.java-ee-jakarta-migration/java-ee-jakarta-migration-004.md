# Đồng bộ Servlet, JPA, Validation và các API Jakarta liên quan

## 1. Bối cảnh: nâng Jakarta không chỉ là sửa import

Khi chuyển hệ thống Java Enterprise từ nền tảng Java EE cũ sang Jakarta EE, lỗi thường xuất hiện ở ranh giới giữa các thành phần tưởng như độc lập: Servlet container, JPA provider, Bean Validation provider, transaction manager, CDI, thư viện JSON/XML, security filter và code sinh tự động.

Một ứng dụng có thể đã thay toàn bộ import trong source từ javax.servlet sang jakarta.servlet nhưng vẫn dùng Servlet container đời cũ chỉ hiểu javax.servlet. Hoặc entity dùng jakarta.persistence nhưng ORM provider, annotation processor và persistence.xml vẫn thuộc thế hệ javax.persistence. Tương tự, các annotation jakarta.validation có thể biên dịch thành công nhưng không được thực thi khi runtime thiếu Bean Validation provider hoặc integration tương ứng.

**Đồng bộ các API Jakarta** nghĩa là lựa chọn một tập hợp nhất quán giữa:

1. Phiên bản Jakarta EE hoặc framework mục tiêu.
2. Namespace API mà source, bytecode và annotations sử dụng.
3. Provider/implementation tương ứng cho Servlet, Persistence, Validation và các dịch vụ khác.
4. Servlet container, application server hoặc embedded runtime.
5. Dependency trực tiếp, bắc cầu, BOM và phạm vi đóng gói.
6. File cấu hình XML, generated source, reflection, service provider và cấu hình deployment.
7. Kiểm thử hợp đồng HTTP, database, validation và transaction trên runtime thực.

Trong **Java Advance Compatibility Migration**, sự chuyển đổi này có thể diễn ra cùng việc nâng JDK và framework. Vì vậy cần nhận biết thay đổi nào đến từ JDK, thay đổi nào đến từ hệ sinh thái Jakarta để xử lý đúng nguyên nhân.

## 2. Phân biệt Java EE, Jakarta EE và Java SE

### 2.1. Các cột mốc namespace

Java EE trước đây cung cấp nhiều Enterprise APIs dưới package javax.*, ví dụ javax.servlet, javax.persistence và javax.validation.

Khi dự án chuyển sang Eclipse Foundation, Jakarta EE ban đầu vẫn duy trì nhiều package javax.* ở thế hệ Jakarta EE 8. **Jakarta EE 9** đánh dấu thay đổi lớn về namespace của phần lớn Enterprise APIs từ javax.* sang jakarta.*.

Do đó:

- Java EE 8 thường dùng javax.servlet, javax.persistence, javax.validation.
- Jakarta EE 8 vẫn chủ yếu dùng những namespace javax.* tương ứng.
- Jakarta EE 9 trở lên chuyển các Jakarta Enterprise APIs liên quan sang jakarta.*.
- Các API Java SE như javax.sql, javax.crypto, javax.xml.parsers hoặc javax.annotation.processing **không** tự chuyển sang jakarta.*.

Nói cách khác, đổi tên package là một sự kiện của Jakarta EE, không phải quy tắc áp dụng cho mọi package bắt đầu bằng javax trên JDK.

### 2.2. Ví dụ ma trận công nghệ

| Thành phần | Nền tảng thế hệ javax | Nền tảng thế hệ jakarta |
|---|---|---|
| Servlet | javax.servlet.* | jakarta.servlet.* |
| Servlet annotations | javax.servlet.annotation.* | jakarta.servlet.annotation.* |
| Persistence / JPA | javax.persistence.* | jakarta.persistence.* |
| Bean Validation | javax.validation.* | jakarta.validation.* |
| Transactions cấp Jakarta EE | javax.transaction.* tương ứng | jakarta.transaction.* |
| CDI | javax.enterprise.* và javax.inject.* | jakarta.enterprise.* và jakarta.inject.* |
| REST / JAX-RS | javax.ws.rs.* | jakarta.ws.rs.* |
| WebSocket | javax.websocket.* | jakarta.websocket.* |
| JSON-B / JSON-P | javax.json.bind.* / javax.json.* | jakarta.json.bind.* / jakarta.json.* |
| Mail/Activation (tùy stack) | javax.mail.* / javax.activation.* | jakarta.mail.* / jakarta.activation.* |

Bảng là hướng nhận diện, không phải lời khuyên thêm đồng thời mọi dependency. Mỗi ứng dụng chỉ nên đưa vào những API thực sự dùng và để nền tảng/framework thống nhất version khi có thể.

### 2.3. Các phiên bản Jakarta EE liên quan

Một ma trận minh họa thường gặp:

| Platform generation | Servlet | Persistence | Bean Validation | Namespace |
|---|---|---|---|---|
| Java EE 8 | Servlet 4.x | JPA 2.2 | Bean Validation 2.x | javax |
| Jakarta EE 9 | Jakarta Servlet 5.0 | Jakarta Persistence 3.0 | Jakarta Bean Validation 3.0 | jakarta |
| Jakarta EE 10 | Jakarta Servlet 6.0 | Jakarta Persistence 3.1 | Jakarta Bean Validation 3.0 | jakarta |

Với các release sau, cần đối chiếu compatibility matrix của platform, framework và application server đã chọn; không nên suy ra rằng cùng namespace jakarta thì mọi major/minor version đều thay thế được cho nhau.

**Điểm then chốt:** package namespace chỉ là một chiều tương thích. Framework, container, ORM/Validation provider và mức Java tối thiểu cũng phải phù hợp.

## 3. Xây dựng một compatibility matrix trước khi đổi source

Trước migration, ghi rõ những thành phần đang chạy và mục tiêu:

| Lớp | Trạng thái hiện tại | Trạng thái dự kiến | Câu hỏi cần xác nhận |
|---|---|---|---|
| JDK runtime | Java cũ | JDK mục tiêu | Framework/provider yêu cầu Java tối thiểu bao nhiêu? |
| Servlet API | javax.servlet | jakarta.servlet | Container có thực thi Jakarta Servlet tương ứng không? |
| Web runtime | Container cũ | Container/embedded runtime mới | WAR và filters có đúng namespace, lifecycle không? |
| Persistence API | javax.persistence | jakarta.persistence | ORM provider và JPA metadata có cùng thế hệ? |
| ORM | Hibernate/EclipseLink thế hệ cũ | Provider hỗ trợ Jakarta Persistence | Entity mapping, DDL, query, caching có thay đổi không? |
| Bean Validation API | javax.validation | jakarta.validation | Provider và integration được gọi thật không? |
| Transactions | JTA/framework transaction cũ | Jakarta Transaction hoặc abstraction hiện hành | Phạm vi commit/rollback giữ đúng không? |
| Injection/CDI | javax.inject/enterprise | jakarta.inject/enterprise | Container có tạo/inject object theo annotations mới? |
| REST/JSON | JAX-RS/JSON-B hoặc framework cũ | Jakarta-compatible stack | DTO/serialization/HTTP status có giữ hợp đồng? |
| Build/runtime dependencies | Nhiều bản transitive | BOM/stack đã đồng bộ | Có duplicate javax/jakarta API hay provider không? |

Ví dụ một lựa chọn có kiểm soát:

~~~text
JDK mục tiêu
      │
      ▼
Jakarta-compatible framework / application server
      │
      ├── Servlet API + container: cùng thế hệ
      ├── Persistence API + ORM provider: cùng thế hệ
      ├── Validation API + implementation: cùng thế hệ
      ├── Transaction integration: phù hợp runtime
      ├── CDI/injection và security: cùng namespace
      └── REST/JSON/WebSocket/Mail nếu ứng dụng dùng
~~~

Không cần mọi API có cùng con số major. Ví dụ Servlet 6.0 và Persistence 3.1 có thể cùng thuộc một bản Jakarta EE platform; điều quan trọng là **tập hợp được nền tảng công bố hỗ trợ**, không phải ép mọi thư viện về cùng “6.0”.

## 4. Đồng bộ Jakarta Servlet và Servlet container

### 4.1. Thay đổi ở source Java

Đối với một servlet cũ:

~~~java
import javax.servlet.ServletException;
import javax.servlet.annotation.WebServlet;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
~~~

Sau khi ứng dụng chuyển sang Jakarta Servlet:

~~~java
import jakarta.servlet.ServletException;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
~~~

Ví dụ một servlet đơn giản:

~~~java
package com.example.web;

import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

@WebServlet("/health")
public class HealthServlet extends HttpServlet {
    @Override
    protected void doGet(HttpServletRequest request,
                         HttpServletResponse response) throws IOException {
        response.setStatus(HttpServletResponse.SC_OK);
        response.setContentType("text/plain;charset=UTF-8");
        response.getWriter().write("OK");
    }
}
~~~

Code trên compile với Jakarta Servlet API phù hợp. Tuy nhiên, nó chỉ hoạt động như servlet khi được chạy trong container hoặc môi trường embedded có hỗ trợ namespace jakarta.servlet tương ứng.

### 4.2. Container thế hệ javax không tải được servlet Jakarta như cũ

Một lỗi thường gặp là code đã đổi import sang jakarta.servlet nhưng vẫn deploy WAR lên container chỉ cung cấp javax.servlet.

Ví dụ về phân biệt thế hệ:

- Dòng container cũ như Tomcat 9 hỗ trợ API Servlet thế hệ javax tương ứng.
- Các dòng container hỗ trợ Jakarta EE 9 trở lên như Tomcat 10.x sử dụng package jakarta.servlet.
- Giữa các dòng Jakarta cũng cần kiểm tra phiên bản Servlet API cụ thể mà container triển khai.

Không nên chỉ dựa vào tên “Tomcat 10” để suy ra bất kỳ Servlet API nào cũng được hỗ trợ: bản minor và release của container liên quan đến Servlet specification được triển khai.

### 4.3. Servlet API do ai cung cấp?

Với WAR deploy lên external servlet container, container thường cung cấp Servlet API ở runtime. Project cần API để compile nhưng không nên đóng gói một bản Servlet API khác bên trong WEB-INF/lib nếu container đã cung cấp phiên bản tương ứng.

Với executable/embedded web application, framework và embedded container phải có đủ runtime implementation, và dependency management của framework thường đảm nhiệm việc đồng bộ các thành phần.

| Kiểu triển khai | Cách tiếp cận dependency |
|---|---|
 WAR trên external Jakarta container | Servlet API thường là compile-only/provided; container cung cấp runtime. |
 Embedded server hoặc executable JAR | Framework/starter hoặc dependency embedded runtime cung cấp Servlet implementation. |
 Full Jakarta EE application server | Server quản lý nhiều API/implementation theo platform; tránh đóng gói trùng theo thói quen. |
 Thư viện cung cấp Servlet Filter | Compile với đúng servlet API; ghi rõ minimum container/runtime mà consumer cần. |

Nếu WAR chứa Servlet API trùng version với container, có thể gây classloading conflict hoặc namespace/version mismatch. Nếu dùng scope provided mà môi trường thật không cung cấp API, ứng dụng có thể lỗi khi khởi động.

### 4.4. Filters, listeners và Spring Security

Đối tượng Servlet quan trọng không chỉ có HttpServlet:

- Filter và FilterChain.
- ServletContextListener, HttpSessionListener.
- HttpServletRequestWrapper và HttpServletResponseWrapper.
- Multipart upload, async servlet.
- RequestDispatcher, ServletContext và các cấu hình error page.
- Security filter chain của framework.

Ví dụ filter sau migration:

~~~java
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import java.io.IOException;

public final class TraceFilter implements Filter {
    @Override
    public void doFilter(ServletRequest request,
                         ServletResponse response,
                         FilterChain chain)
            throws IOException, ServletException {
        chain.doFilter(request, response);
    }
}
~~~

Một Filter class được biên dịch cho javax.servlet.Filter **không** phải implementation của jakarta.servlet.Filter. Vì vậy, ngoài source project, phải nâng các filter do thư viện bên ngoài cung cấp, chẳng hạn tracing, security, SSO, metrics hoặc upload framework.

### 4.5. Web descriptor và servlet mapping

Nếu ứng dụng dùng web.xml, việc đổi import Java là chưa đủ. File XML có thể khai báo namespace/schema và cấu trúc cấu hình theo Servlet specification thế hệ cũ.

Ví dụ descriptor dành cho Jakarta Servlet 6.0:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           https://jakarta.ee/xml/ns/jakartaee
           https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
         version="6.0">
</web-app>
~~~

Schema và version phải phù hợp container đã chọn. Với ứng dụng có security constraints, filters, servlet declarations, listeners và session configuration, cần kiểm tra toàn bộ descriptor chứ không chỉ thay xmlns.

## 5. Đồng bộ Jakarta Persistence (JPA) và ORM provider

### 5.1. JPA là API; Hibernate/EclipseLink là provider

Jakarta Persistence định nghĩa API cho entity, mapping, EntityManager, JPQL, lifecycle và persistence context. Một ORM provider như Hibernate ORM hoặc EclipseLink thực thi các hoạt động đó.

Thay:

~~~java
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.EntityManager;
~~~

bằng:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.EntityManager;
~~~

chỉ là thay đổi một phần. Provider, runtime integration, generated metamodel, persistence.xml, transaction manager và dependency graph cũng phải nhận ra jakarta.persistence.

### 5.2. Ví dụ entity theo Jakarta Persistence

~~~java
package com.example.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String displayName;

    protected Customer() {
        // Constructor cho JPA.
    }

    public Customer(String displayName) {
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Entity này dùng Jakarta Persistence annotations. Một provider đời cũ chỉ tìm javax.persistence.Entity có thể không nhận ra entity hoặc không tạo mapping đúng. Bổ sung jakarta.persistence-api vào compile classpath không biến provider cũ thành provider Jakarta-compatible.

### 5.3. Chọn bộ API và ORM tương thích

| Thành phần | Cần đồng bộ |
|---|---|
| Entity annotations | jakarta.persistence.*. |
| Persistence API | Phiên bản Jakarta Persistence phù hợp platform/framework. |
| ORM runtime | Provider hỗ trợ phiên bản API tương ứng. |
| Entity manager factory | Bootstrap từ framework/container hoặc Persistence API đúng hệ. |
| Transaction manager | JTA/JDBC/framework transaction phù hợp provider. |
| Persistence metadata | persistence.xml, orm.xml và mapping files theo schema tương ứng. |
| Annotation processor | Static metamodel generator hoặc enhancer dùng đúng thế hệ annotations. |
| Database/JDBC driver | Driver chạy được trên JDK và ORM runtime được chọn. |
| Cache | Second-level cache/provider, cache key và serialization tương thích. |

Ví dụ, nâng từ Hibernate ORM thế hệ dùng javax.persistence sang Hibernate ORM thế hệ hỗ trợ jakarta.persistence có thể cần cập nhật cả API, code, persistence metadata và các thư viện tích hợp của framework. Không nên ép version Hibernate thủ công vượt xa framework BOM nếu chưa xác minh compatibility.

### 5.4. persistence.xml và XML namespace

Đối với ứng dụng dùng JPA bootstrap bằng persistence.xml, file thường nằm tại META-INF/persistence.xml. Khi chuyển generation, cần kiểm tra:

- Namespace và version của persistence descriptor.
- Provider class và properties.
- Persistence-unit transaction type.
- Data source và JDBC settings.
- Mapping files.
- Provider-specific property names đã deprecated/đổi tên.

Ví dụ descriptor Jakarta Persistence 3.1 minh họa:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="
               https://jakarta.ee/xml/ns/persistence
               https://jakarta.ee/xml/ns/persistence/persistence_3_1.xsd"
             version="3.1">
    <persistence-unit name="appPU">
        <class>com.example.domain.Customer</class>
    </persistence-unit>
</persistence>
~~~

Với framework tự cấu hình persistence unit, dự án có thể không cần file này. Không tạo persistence.xml chỉ vì chuyển namespace; hãy dựa trên cách bootstrap thực tế.

### 5.5. JPQL, schema generation và database behavior

Thay provider JPA có thể thay đổi cả hành vi ngoài namespace:

- Cách dịch JPQL/HQL sang SQL và dialect.
- Chiến lược sinh ID, sequence, identity và allocation size.
- Schema validation hoặc DDL generation.
- Lazy loading và thời điểm nạp association.
- Cascade, orphan removal và dirty checking.
- Flush mode, transaction boundaries và optimistic locking.
- JDBC batching, query plan và paging.
- Mapping Enum, JSON, temporal, UUID, embeddable.
- Cache, statistics và generated queries.

Khi migration, test cần xác nhận dữ liệu, constraint, transaction và SQL behavior thay vì chỉ kiểm tra EntityManager khởi động thành công.

### 5.6. Không để javax.persistence tồn tại trong public/domain API mới

Ví dụ một repository mới sử dụng jakarta.persistence.EntityManager nhưng vẫn nhận javax.persistence.criteria.Predicate từ một thư viện cũ sẽ không thể nối hai type system như những type đồng nhất.

Tốt hơn:

1. Nâng repository và thư viện phụ trợ lên bộ JPA API cùng thế hệ.
2. Nếu consumer cũ chưa thể nâng, đặt một adapter tại ranh giới API có kiểm soát.
3. Tránh truyền đối tượng EntityManager, Predicate hoặc annotation metadata qua bridge giữa hai thế hệ.
4. Kiểm thử lại public API và binary compatibility nếu có consumer độc lập.

Thông thường, tách deployment/service hoặc chuyển toàn bộ module persistence theo một mốc rõ ràng dễ bảo trì hơn việc cố chạy hai ORM provider khác thế hệ trên cùng persistence context.

## 6. Đồng bộ Jakarta Bean Validation

### 6.1. API, provider và integration

Bean Validation dùng các annotation như NotNull, NotBlank, Size, Min, Max, Email, Valid và cơ chế Validator để kiểm tra constraint của object.

Trước migration:

~~~java
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
import javax.validation.constraints.Size;
~~~

Sau migration:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
~~~

Cần phân biệt:

1. **Jakarta Validation API** chứa annotations và interface.
2. **Validation provider** cung cấp implementation, ví dụ một Hibernate Validator release phù hợp.
3. **Integration** giúp framework gọi validator vào thời điểm mong muốn: nhận HTTP request, gọi service method, persistence lifecycle hoặc CDI.

Việc có @NotBlank trong bytecode **không** tự làm một POJO được kiểm tra ở mọi điểm sử dụng.

### 6.2. Ví dụ DTO sử dụng jakarta.validation

~~~java
package com.example.api;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class RegisterCustomerRequest {
    @NotBlank
    @Size(max = 120)
    private String displayName;

    @NotBlank
    @Email
    private String email;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

Ở ví dụ trên, validation được thực thi khi ứng dụng thực sự gọi Validator hoặc framework tích hợp Bean Validation cho request. Nếu chỉ compile annotations và deserialize JSON, constraint có thể không được kiểm tra.

### 6.3. Ví dụ validation độc lập

~~~java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import java.util.Set;

public final class ValidationExample {
    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            RegisterCustomerRequest request = new RegisterCustomerRequest();
            request.setDisplayName("");
            request.setEmail("not-an-email");

            Set<ConstraintViolation<RegisterCustomerRequest>> violations =
                    validator.validate(request);

            System.out.println(violations.size());
        }
    }
}
~~~

Ở đây cần có Jakarta Validation API và provider tương ứng trên runtime classpath. Cơ chế xử lý thông báo có thể cần thành phần Expression Language phù hợp tùy provider/cấu hình interpolation. Trong môi trường quản lý bởi framework/container, thường nên inject Validator hoặc sử dụng cấu hình có sẵn thay vì tạo ValidatorFactory tùy tiện ở mỗi request.

### 6.4. Những trường hợp validation dễ thay đổi

| Khu vực | Cần xác minh |
|---|---|
| Request DTO | @Valid/@Validated có được framework gọi và map lỗi đúng HTTP contract? |
| Nested object | @Valid thực sự kích hoạt cascade validation cho field nested? |
| Collection | Các constraint trên phần tử list/map còn hoạt động theo provider/spec mới? |
| Method validation | Interceptor/proxy có áp dụng cho phương thức service? |
| JPA lifecycle | Entity validation được gọi theo chính sách persistence và group? |
| Custom constraint | Validator class implement đúng jakarta.validation.ConstraintValidator? |
| Groups | Group sequences, default group và conversion có đúng? |
| Message interpolation | Message bundle, locale và EL provider có sẵn? |
| Violation mapping | Property path, error code, HTTP response và thông điệp có ổn định? |

Ví dụ custom constraint validator cũ implement javax.validation.ConstraintValidator không tự trở thành Jakarta validator bằng cách chỉ đổi annotation ở DTO.

### 6.5. Custom constraint migration

Source legacy:

~~~java
import javax.validation.Constraint;
import javax.validation.ConstraintValidator;
import javax.validation.ConstraintValidatorContext;
~~~

Với Jakarta:

~~~java
import jakarta.validation.Constraint;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
~~~

Ngoài import, cần kiểm tra:

- Annotation @Constraint(validatedBy = ...) có tham chiếu đúng class.
- Generic type của ConstraintValidator phù hợp dữ liệu.
- Default message, groups, payload và retention/target giữ đúng.
- Validator provider phát hiện implementation.
- Message bundles và locale được tải đúng classloader.

### 6.6. Tránh nhầm hai ConstraintViolationException

Một tình huống dễ gây xử lý sai:

- jakarta.validation.ConstraintViolationException biểu diễn các vi phạm Bean Validation.
- org.hibernate.exception.ConstraintViolationException là loại exception riêng của Hibernate ORM, thường liên quan vi phạm database constraint.

Tên đơn giản giống nhau nhưng semantics và package khác nhau. Khi viết exception handler trong API sau migration, hãy dùng fully qualified type/đúng import và xác định HTTP status phù hợp; không gom tùy tiện cả hai thành một loại lỗi.

## 7. Đồng bộ Servlet, Persistence và Validation thành một luồng

Ba API thường tham gia chung một request:

~~~text
HTTP client
    │
    ▼
Jakarta Servlet container / web framework
    │  Parse request + authentication
    ▼
Request DTO
    │
    ▼
Jakarta Bean Validation
    │  Validate input / reject invalid data
    ▼
Application service
    │  Authorization + business rules
    ▼
Transaction boundary
    │
    ▼
Jakarta Persistence + ORM provider
    │
    ▼
Database / JDBC driver
    │
    ▼
Response mapping / HTTP status
~~~

Đồng bộ cần đảm bảo rằng request đi trọn luồng:

1. Container chấp nhận Servlet/JAX-RS classes ở namespace mới.
2. Framework chuyển request thành DTO đúng.
3. Validator provider kiểm tra constraints và trả lỗi đúng chính sách.
4. Service thực thi authorization trước khi sửa dữ liệu.
5. Transaction và EntityManager được điều phối chính xác.
6. ORM thực thi SQL, commit/rollback và map exception có kiểm soát.
7. Response giữ wire contract hoặc thay đổi có versioning.

Một module chỉ compile thành công ở từng lớp không chứng minh liên kết xuyên các lớp đang hoạt động. Ví dụ Validation API có mặt nhưng controller không kích hoạt validation; entity dùng @NotNull nhưng exception xảy ra chỉ khi database từ chối vì column NOT NULL.

### 7.1. Hai lớp constraint không thay thế nhau

Bean Validation kiểm tra object theo rules đã khai báo, còn database constraints cưỡng chế tính toàn vẹn ở database. Một trường email bắt buộc có thể được kiểm tra ở DTO và entity, nhưng vẫn cần constraint database khi thích hợp.

Trong migration:

- Đảm bảo invalid input bị xử lý ở boundary theo API contract.
- Giữ database constraints quan trọng, không bỏ chỉ vì có @NotNull.
- Test concurrency và transaction rollback nếu database reject ở thời điểm flush/commit.
- Phân biệt lỗi validation nghiệp vụ với lỗi persistence/hạ tầng trong response.

## 8. Jakarta Transactions và ranh giới transaction

Transactions liên kết Persistence với service layer. Khi chuyển stack, cần xác định ai quản lý transaction:

- Jakarta Transaction API và transaction manager của application server.
- Spring transaction abstraction và transaction manager tương ứng.
- Resource-local JPA transactions trong ứng dụng standalone.
- Distributed/XA transaction nếu thực sự dùng.

Đối với Jakarta:

~~~java
import jakarta.transaction.Transactional;
~~~

Trong Spring, cũng có annotation:

~~~java
import org.springframework.transaction.annotation.Transactional;
~~~

Hai annotation này không phải cùng một class Java; cơ chế integration cụ thể quyết định runtime xử lý chúng như thế nào. Không nên đổi toàn bộ transaction annotations bằng thao tác tìm-thay mà không kiểm tra transaction manager, framework version và rollback semantics.

### 8.1. Các hành vi cần kiểm thử

- Transaction bắt đầu và kết thúc ở đúng service/use case.
- Lỗi validation có gây rollback theo policy hay không.
- Database constraint violation xuất hiện ở flush hay commit.
- Checked exception và runtime exception kích hoạt rollback theo rule đã công bố.
- Lazy-loaded association không được truy cập sau khi persistence context đóng nếu không có kế hoạch.
- Tác vụ async hoặc scheduled job có transaction context đúng.
- Nested operations/propagation, timeout, locking và isolation không thay đổi vô tình.

Một hệ thống có thể chuyển provider mà kết quả CRUD đơn giản vẫn đúng, nhưng khi gặp lỗi ở giữa batch lại commit một phần. Đó là regression nghiệp vụ cần test, không chỉ lỗi API namespace.

### 8.2. javax.transaction.xa vẫn là điểm cần phân biệt

Không phải mọi package javax.transaction đều phải đổi. Các kiểu XA như javax.transaction.xa.XAResource vẫn liên quan Java SE/JDBC và không nên bị rename tự động chỉ vì đang migration Jakarta Transaction APIs.

Điều này cùng quy tắc với javax.sql, javax.crypto và các package Java SE khác: xác định module/API sở hữu trước khi đổi.

## 9. Đồng bộ CDI, dependency injection và vòng đời

Nhiều ứng dụng Jakarta dùng CDI hoặc một DI framework để tạo servlet collaborators, persistence services, validators và transaction integrations.

Các annotation cần xem xét:

~~~text
javax.inject.Inject          -> jakarta.inject.Inject
javax.inject.Named           -> jakarta.inject.Named
javax.enterprise.context.*   -> jakarta.enterprise.context.*
javax.annotation.PostConstruct -> jakarta.annotation.PostConstruct
~~~

Đây là hướng đối chiếu ở phần APIs thuộc Jakarta EE, không phải quy tắc đổi toàn bộ javax namespace.

### 9.1. Một import đúng không chứng minh injection đã chạy

Ví dụ field:

~~~java
import jakarta.inject.Inject;

public class CustomerController {
    @Inject
    CustomerService customerService;
}
~~~

Nếu CustomerController được tạo bằng new trong một ứng dụng Java SE không có injection container hoặc cơ chế injection phù hợp, customerService sẽ không tự có giá trị chỉ vì annotation hiện diện.

Trong migration, cần kiểm tra bean discovery, scanning, lifecycle, proxy và integration:

- beans.xml và discovery mode khi áp dụng.
- Sự khác nhau giữa container-managed và manually-created objects.
- Tên package được scanner include/exclude.
- Các interceptor và decorators.
- Scope request/session/application.
- Initialization/disposal và @PostConstruct/@PreDestroy.

Nếu framework thay cách phát hiện component giữa các major versions, test phải thực sự khởi tạo application context và gọi qua entry point, không chỉ kiểm tra code compile.

## 10. REST, JSON, WebSocket và các Jakarta API liên quan

Servlet/JPA/Validation thường liên quan đến nhiều API Enterprise khác:

| API | Namespace Jakarta | Tác động migration |
|---|---|---|
| Jakarta RESTful Web Services | jakarta.ws.rs.* | Resource annotations, filters, client/server provider và exception mappers. |
| Jakarta JSON Binding | jakarta.json.bind.* | Serialize/deserialize DTO, adapters, property names và null handling. |
| Jakarta JSON Processing | jakarta.json.* | Streaming/DOM JSON APIs và provider. |
| Jakarta WebSocket | jakarta.websocket.* | Endpoint, session, handshakes và implementation của container. |
| Jakarta Messaging | jakarta.jms.* | Connection factories, broker client, transactions và provider. |
| Jakarta Mail | jakarta.mail.* | MIME, SMTP/IMAP clients, Activation và runtime provider. |
| Jakarta XML Binding | jakarta.xml.bind.* | JAXB annotations, runtime provider và generated classes. |
| Jakarta Security | jakarta.security.enterprise.* | Authentication/identity store integration với container. |

Chỉ đưa những API cần thiết vào dependency graph. Nếu framework đã quản lý JSON, REST hoặc Servlet integration, tránh thêm một runtime provider khác có thể cạnh tranh service discovery.

### 10.1. REST và Bean Validation

Với một endpoint nhận JSON:

~~~java
import jakarta.validation.Valid;
import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.core.MediaType;

@Path("/customers")
public class CustomerResource {
    @POST
    @Consumes(MediaType.APPLICATION_JSON)
    public void create(@Valid RegisterCustomerRequest request) {
        // Delegation to service.
    }
}
~~~

Đoạn trên cần Jakarta REST runtime và Validation integration đúng stack mới có ý nghĩa. Không nên mặc định mọi JAX-RS implementation đều tự kích hoạt cùng một Bean Validation provider nếu chưa kiểm tra cấu hình/bộ API được hỗ trợ.

Ngoài annotations, phải kiểm tra return code, JSON field names, error response và filters; đổi serializer/provider có thể làm wire contract thay đổi dù URL vẫn giữ nguyên.

### 10.2. WebSocket/JSON-B/XML

Với WebSocket, cần kiểm tra handshake, endpoint registration và message converter theo version container. Với JSON-B/XML, thay namespace có thể kéo theo provider mới, làm thay đổi cách parse thời gian, enum, null hoặc XML schema.

Khi dùng source generated từ WSDL/XSD/OpenAPI, generator phải thuộc thế hệ tương thích. Generated files chứa javax.* thường cần regenerate bằng tool phù hợp, không chỉ sửa file Java viết tay.

## 11. Maven và Gradle: quản lý version tập trung

### 11.1. BOM và platform có vai trò gì?

Trong Jakarta migration, chọn riêng lẻ nhiều version API/provider rất dễ dẫn đến lệch bộ. Có thể dùng:

- BOM của Jakarta EE platform nếu triển khai theo platform và dùng các API được BOM quản lý.
- BOM/parent của framework như Spring Boot khi ứng dụng thuộc framework đó.
- Dependency management chính thức của application server/runtime.
- Constraints hoặc version catalog được tổ chức quản lý.

**BOM giúp quản lý version**, nhưng không tự đảm bảo provider tương thích nếu bạn cố tình override những thành phần ngoài bộ hỗ trợ. Cũng không phải mọi BOM chứa cả ORM, Validation provider, servlet container và driver ở cùng mức.

### 11.2. Ví dụ Maven với dependencyManagement

Ví dụ dùng BOM Jakarta EE 10 ở phạm vi minh họa:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>jakarta.platform</groupId>
            <artifactId>jakarta.jakartaee-bom</artifactId>
            <version>10.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>jakarta.servlet</groupId>
        <artifactId>jakarta.servlet-api</artifactId>
        <scope>provided</scope>
    </dependency>
</dependencies>
~~~

Đây là một ví dụ nền tảng Jakarta EE 10; khi áp dụng phải xác nhận artifact BOM, version và scope theo stack dự án. Việc import BOM không thêm tất cả các API hoặc runtime provider vào ứng dụng; dependency vẫn phải được khai báo hoặc được runtime container cung cấp.

Với full Jakarta EE application server, có thể dùng API aggregate theo hướng dẫn của server thay vì khai báo từng API. Với embedded application, lại cần các runtime implementations được framework quản lý.

### 11.3. Ví dụ Gradle Kotlin DSL theo platform

~~~kotlin
plugins {
    java
}

dependencies {
    compileOnly(platform("jakarta.platform:jakarta.jakartaee-bom:10.0.0"))
    compileOnly("jakarta.servlet:jakarta.servlet-api")
    compileOnly("jakarta.persistence:jakarta.persistence-api")
    compileOnly("jakarta.validation:jakarta.validation-api")
}
~~~

Đây là ví dụ cho module compile với API do **external Jakarta EE runtime** cung cấp. Không sử dụng cấu hình compileOnly này nếu ứng dụng standalone cần tự đóng gói API/provider mà không có runtime cung cấp. Chọn scope dựa trên packaging và deployment thực tế.

Với ứng dụng Spring Boot, thường ưu tiên dependency management/starter của phiên bản Spring Boot đã chọn thay vì tự lắp ghép từng Servlet/JPA/Validation API và provider.

### 11.4. Xem resolved dependency graph

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jakarta.persistence \
    --configuration runtimeClasspath
~~~

Maven:

~~~bash
./mvnw dependency:tree
~~~

Các lệnh giúp trả lời:

- Một artifact javax.* còn bị kéo vào từ thư viện nào?
- Jakarta API có mặt ở compile nhưng thiếu runtime provider không?
- Có nhiều bản Servlet/Persistence/Validation API cùng được resolve không?
- Servlet API được đóng gói vào WAR hay do container cung cấp?
- Có override framework BOM làm mất compatibility không?

Cần chú ý: **cả javax và jakarta có thể cùng xuất hiện ở classpath vì một thư viện dùng Java SE javax API vẫn hoàn toàn hợp lệ**. Không xóa mọi dependency có tiền tố javax một cách máy móc.

## 12. Sự khác nhau giữa API JAR và runtime implementation

| Công nghệ | API | Runtime/implementation |
|---|---|---|
| Servlet | jakarta.servlet-api | Servlet container như Tomcat/Jetty/Undertow đời tương thích. |
| Persistence | jakarta.persistence-api | ORM/JPA provider như Hibernate ORM hoặc EclipseLink đời phù hợp. |
| Bean Validation | jakarta.validation-api | Hibernate Validator hoặc provider khác tương thích. |
| CDI | jakarta.enterprise.cdi-api, injection APIs | CDI container/integration tương ứng. |
| Jakarta REST | jakarta.ws.rs-api | JAX-RS runtime/provider tương thích. |
| JSON-B | jakarta.json.bind-api | JSON-B implementation phù hợp. |
| JAXB | jakarta.xml.bind-api | JAXB runtime implementation phù hợp. |

Một số application servers hoặc framework starters đã phân phối API/provider; khai báo thủ công có thể gây version conflict. Ngược lại, một dependency chỉ cung cấp API làm code compile nhưng không cung cấp runtime chức năng.

### 12.1. Các lỗi runtime điển hình

| Lỗi | Nguyên nhân có thể |
|---|---|
| ClassNotFoundException: jakarta.servlet.Filter | Servlet API/runtime chưa có hoặc ứng dụng chạy container thế hệ javax. |
| NoClassDefFoundError: javax.persistence.Entity | Dependency chưa chuyển sang Jakarta hoặc runtime legacy class bị thiếu. |
| Bean Validation provider not found | Có jakarta.validation-api nhưng thiếu implementation phù hợp. |
| Not a managed type / Unknown entity | ORM provider không nhận entity, mapping/scanning/persistence unit không phù hợp. |
| AbstractMethodError / NoSuchMethodError | API và provider hoặc các dependency liên quan không khớp version. |
| InaccessibleObjectException | Provider/framework dùng reflection vào package không được mở theo JPMS. |
| ServiceConfigurationError | Service provider metadata chỉ đến class sai hoặc provider trộn thế hệ. |

Những thông báo này chỉ định hướng điều tra; cần xem stack trace, classloader, runtime artifact và dependency graph thực tế trước khi kết luận.

## 13. Namespace mismatch ở binary level

Java phân biệt class bằng fully qualified binary name. javax.servlet.Filter và jakarta.servlet.Filter là hai interface khác nhau; javax.persistence.EntityManager và jakarta.persistence.EntityManager cũng vậy.

Nếu class được biên dịch với javax.servlet.Filter:

~~~text
LegacyFilter implements javax.servlet.Filter
~~~

nó không thể tự trở thành:

~~~text
ModernFilter implements jakarta.servlet.Filter
~~~

chỉ bằng việc thêm jakarta.servlet-api.jar vào runtime. JVM vẫn thấy hai binary names khác nhau.

Tương tự, annotation javax.persistence.Entity không đồng nhất với jakarta.persistence.Entity, nên ORM provider chỉ quét annotation thế hệ Jakarta có thể không nhận entity legacy.

### 13.1. Tác động đối với public API

Giả sử một library đã công bố method:

~~~java
public void register(javax.servlet.Filter filter);
~~~

Sau migration thành:

~~~java
public void register(jakarta.servlet.Filter filter);
~~~

Đây là thay đổi method descriptor và vì thế là **breaking binary API change**. Client biên dịch với version cũ không thể tự động gọi method mới. Cần versioning rõ ràng, có thể dùng adapter/bridge nếu phạm vi cho phép hoặc duy trì nhánh tương thích trong khoảng thời gian chuyển tiếp.

### 13.2. Không nên cố giữ cả hai hệ ở một classloader không kiểm soát

Một ứng dụng lớn có thể tạm thời mang các JAR javax và jakarta để phục vụ những module độc lập. Tuy vậy:

- Provider và framework scanner có thể chỉ hiểu một hệ.
- Các annotation không tự đổi nghĩa.
- Java binary signatures vẫn khác nhau.
- Container có một servlet namespace làm hợp đồng triển khai.
- Hai ORM providers sử dụng cùng database/entity model có thể gây lifecycle và transaction conflict.

Nếu cần hỗ trợ hệ cũ và mới đồng thời, đặt ranh giới rõ: process/service riêng, adapter qua giao thức trung gian hoặc kế hoạch chuyển đổi có kiểm soát. Không coi việc hai package có thể cùng tồn tại trên classpath là bảo đảm toàn bộ ứng dụng hoạt động.

## 14. Generated code và metadata thường bị bỏ sót

Các hệ thống enterprise có nhiều thành phần không phải Java source viết tay:

1. Code generated từ OpenAPI, WSDL, XSD.
2. JPA static metamodel classes.
3. Annotation processor output.
4. Servlet filters/initializers từ thư viện thứ ba.
5. JAX-RS resource proxies, CDI decorators.
6. XML descriptors: web.xml, persistence.xml, orm.xml, validation.xml.
7. META-INF/services, extension/discovery files.
8. Framework auto-configuration và reflection metadata.
9. Test fixtures hoặc mock classes implement API cũ.

### 14.1. JPA static metamodel

Ví dụ source generated có:

~~~java
import javax.persistence.metamodel.SingularAttribute;
~~~

thì dù entity đã đổi sang jakarta.persistence, generated metamodel vẫn thuộc thế hệ javax và gây mismatch. Cần dùng processor hỗ trợ Jakarta Persistence và regenerate source/bytecode từ entity mới.

### 14.2. validation.xml

Nếu ứng dụng dùng META-INF/validation.xml, kiểm tra namespace/schema và provider class theo Jakarta Validation version mục tiêu. Các constraint mapping files, message bundle và config XML cũng phải được kiểm chứng.

Không tạo một validation.xml mới khi framework đang dùng defaults phù hợp nếu không cần; nhưng nếu file cũ tồn tại thì phải xác định nó được parser nào đọc.

### 14.3. Classpath service discovery

Một số providers được phát hiện qua Java ServiceLoader hoặc metadata META-INF/services. Tên interface trong service descriptor là binary name, nên tên javax.* cũ không thể đảm nhận đăng ký cho jakarta.* tương ứng.

Nếu đóng gói fat JAR/shading, cần kiểm tra merging của META-INF/services. Nếu merger xóa service entries, validation/JPA/JSON runtime có thể không tìm provider dù dependency đã được đóng gói.

### 14.4. Reflection và JPMS

Trên module path, Java có ranh giới exports/opens. JPA và Validation providers có thể dùng reflection để truy cập field/constructor:

- Kiểm tra module-info.java khi dự án dùng JPMS.
- Xác định package cần opens cho framework/provider.
- Không mở tràn lan toàn bộ module chỉ để loại lỗi.
- Kiểm tra đúng JDK, runtime provider và mode classpath/module path được triển khai.

Nâng Jakarta không bắt buộc chuyển mọi ứng dụng sang JPMS, nhưng nếu ứng dụng đã dùng module path thì cần kiểm thử cả ràng buộc module.

## 15. Migration trong Spring-based application

Một trường hợp thường gặp là ứng dụng từ Spring Framework/Spring Boot thế hệ cũ chuyển lên dòng framework sử dụng Jakarta APIs.

Những hạng mục liên quan:

- Spring MVC/Servlet request pipeline.
- Spring Security filters và authentication.
- JPA/Hibernate integration và transaction manager.
- Jakarta Bean Validation được framework tích hợp.
- Embedded servlet container.
- JSON serialization.
- Exception handling và API error response.
- JDK minimum theo framework release.

### 15.1. Vì sao nên dùng starter/BOM?

Trong ứng dụng Spring Boot, dependency management của release mục tiêu thường lựa chọn bộ Spring, Hibernate, validation provider và embedded container đã được thiết kế hoạt động cùng nhau. Nếu khai báo một Hibernate ORM hoặc Servlet API version lệch hẳn với starter, có thể phá binary/runtime compatibility.

Do đó:

1. Chọn framework release theo compatibility matrix và JDK target.
2. Dùng starters/dependency management theo framework.
3. Chuyển source/import và integration modules tương ứng.
4. Chỉ override dependency khi có lý do được kiểm chứng, chẳng hạn security fix.
5. Chạy integration tests qua framework application context và embedded container thực tế.

### 15.2. Không trộn framework có hai thế hệ Servlet API

Ví dụ một security filter jar được build cho javax.servlet.Filter không thể trở thành filter của Jakarta Servlet container. Cần bản library được xây dựng cho Jakarta stack.

Tương tự, một plugin ORM khai báo javax.persistence.EntityManager không thể nhận jakarta.persistence.EntityManager như thể cùng type. Trước khi nâng framework, cần kiểm kê các tích hợp third-party vốn gắn chặt với Servlet/JPA/Validation để tránh bị chặn ở phút cuối.

## 16. Kiểm thử từng lớp sau khi đồng bộ

### 16.1. Servlet HTTP contract tests

Kiểm tra:

- Context path, servlet registration và URL mappings.
- Filters/listeners hoạt động đúng thứ tự.
- Content type, character encoding, multipart upload.
- Session, cookie flags, CSRF, CORS và security behavior.
- Async request handling và timeout.
- Error pages, exception translation, HTTP status.
- Hoạt động khi deploy WAR hoặc chạy embedded tùy loại artifact.

Không chỉ unit test trực tiếp service. Một lỗi filter registration chỉ lộ khi đi qua HTTP runtime thật.

### 16.2. Persistence integration tests

Kiểm tra:

- Entity scanning, @Entity/@Id và field mapping.
- EntityManagerFactory/EntityManager bootstrap.
- Insert/update/delete, flush/commit và rollback.
- Lazy/eager loading, cascade, orphan removal.
- JPQL/criteria queries, pagination, sorting và locking.
- Generated IDs và migration schema.
- Database constraints, JDBC dialect và timezone.
- Transaction boundaries và second-level cache khi sử dụng.

Nên sử dụng DB/container test tương ứng môi trường thật đối với những behavior phụ thuộc dialect. Một embedded database khác vendor không thể chứng minh toàn bộ SQL behavior production.

### 16.3. Bean Validation tests

Kiểm tra:

- DTO có lỗi bị phát hiện.
- DTO hợp lệ vượt qua validation.
- Nested @Valid hoạt động.
- Custom validators được gọi.
- Method validation ở đúng service boundary.
- Constraint groups và messages.
- HTTP mapping của constraint violations.
- JPA lifecycle validation nếu dự án cần.

Test cần phân biệt “annotation xuất hiện trong source” và “runtime gọi validator thực sự”. Có thể test Validator trực tiếp và một integration test qua HTTP/service framework.

### 16.4. Cross-layer tests

Một test quan trọng:

~~~text
POST /customers với payload không hợp lệ
    → Servlet/JAX-RS route được nhận
    → Bean Validation phát hiện lỗi
    → Không tạo bản ghi trong database
    → HTTP error contract ổn định

POST /customers với payload hợp lệ
    → Authentication/authorization hợp lệ
    → Service bắt đầu transaction
    → ORM persist entity
    → Commit thành công
    → Response chứa ID đúng định dạng
~~~

Một bài test riêng nữa cần gây lỗi tại database hoặc business rule để xác minh rollback. Nếu constraint được thực thi ở flush/commit, lỗi có thể xảy ra muộn hơn bước DTO validation.

## 17. Triệu chứng và cách điều tra

| Triệu chứng | Nguyên nhân có thể | Điều tra |
|---|---|---|
| ClassNotFoundException jakarta.servlet.* | Chạy trên container cũ hoặc thiếu Servlet runtime API. | Kiểm tra WAR/JAR, server version và classloader. |
| ServletException khi startup filter | Third-party filter dùng javax.servlet. | Xem interface được implement và dependency origin. |
| Not a managed type | Entity annotation chưa đổi, scanning hoặc JPA provider lệch. | Kiểm tra entity import, provider và entity packages. |
| EntityManagerFactory không tạo được | Provider, persistence unit, schema hoặc JDBC config sai. | Xem root cause và resolved versions. |
| Validation provider missing | Có API nhưng thiếu implementation. | Kiểm tra classpath/provider metadata và framework starter. |
| @Valid không chạy | Chưa kích hoạt validation integration hoặc code path không qua framework. | Integration test qua controller/service runtime. |
| NoSuchMethodError / AbstractMethodError | Provider và API/framework version không khớp. | Truy đúng JAR đã nạp; kiểm tra BOM/overrides. |
| Transaction không rollback | Transaction manager/proxy/annotation semantics thay đổi. | Test fail path, propagation và rollback rules. |
| 404 hoặc filter không áp dụng | Servlet mapping, context path hay security chain thay đổi. | Test qua deployment thật và descriptor/annotations. |
| HTTP response khác schema | Serializer/provider mới, exception mapper thay đổi. | Contract snapshots và behavior tests. |
| InaccessibleObjectException | Reflection bị module restrictions hoặc library cũ. | Kiểm tra JPMS, framework provider và JDK. |

Không có một câu lệnh thay namespace nào chữa mọi triệu chứng. Luôn xác định lớp lỗi: compile, dependency resolution, classloading, provider discovery, bootstrap, nghiệp vụ hay deployment.

## 18. Các công cụ và phương pháp rà soát source/dependency

### 18.1. Quét Java imports

Trong project có ripgrep:

~~~bash
rg -n "javax[.](servlet|persistence|validation|ws[.]rs|inject|enterprise|transaction|annotation)" src
rg -n "jakarta[.](servlet|persistence|validation|ws[.]rs|inject|enterprise|transaction|annotation)" src
~~~

Đây là cách tìm sơ bộ. Những package javax của Java SE vẫn phải được giữ nếu ứng dụng dùng, và source generated/configuration có thể không nằm dưới src.

### 18.2. Quét XML và service metadata

Tìm trong:

~~~text
src/main/webapp/WEB-INF/web.xml
src/main/resources/META-INF/persistence.xml
src/main/resources/META-INF/validation.xml
src/main/resources/META-INF/orm.xml
META-INF/services/
Generated sources
Framework-specific descriptors
~~~

Cấu trúc đường dẫn tùy dự án. Không nhất thiết file nào cũng tồn tại.

### 18.3. Kiểm tra artifact và runtime dependencies

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jakarta.validation \
    --configuration runtimeClasspath
~~~

Maven:

~~~bash
./mvnw dependency:tree
~~~

Classpath thực tế của deployment có thể khác build tree vì external application server cung cấp libraries. Khi có lỗi NoClassDefFoundError hoặc LinkageError, phải ghi nhận JAR location/classloader đã nạp.

### 18.4. Công cụ tự động chuyển namespace

Một số công cụ hỗ trợ chuyển javax sang jakarta ở source, bytecode hoặc deployment archive, chẳng hạn migration recipes của OpenRewrite hay công cụ chuyển đổi Java EE/Jakarta dành cho application deployment.

Chúng có thể giảm công việc cơ học nhưng không tự:

- Chọn đúng ORM/Validation provider.
- Nâng Servlet container.
- Sửa transaction semantics.
- Đảm bảo phương thức cũ vẫn binary compatible.
- Điều chỉnh database schema, query và HTTP contract.
- Chứng minh integration tests qua topology thật.

Vì vậy, phải xem kết quả chuyển đổi như **một bước của migration**, không phải bằng chứng kết thúc.

## 19. Một lộ trình triển khai có kiểm soát

### Giai đoạn A — Kiểm kê và chốt baseline

1. Ghi JDK, framework, container, Servlet API, ORM provider, Validation provider và runtime artifacts.
2. Lưu resolved dependency graph của compile/runtime.
3. Xác định modules dùng javax.*, modules đã dùng jakarta.* và các Java SE javax APIs không đổi.
4. Lưu HTTP/API contract, JPA queries và test dữ liệu đại diện.
5. Liệt kê generated code, XML descriptors, third-party filters và integrations.

### Giai đoạn B — Chọn target stack

1. Chọn framework/Jakarta EE platform và phiên bản container phù hợp.
2. Chọn bộ JPA/ORM, Validation provider và transaction integration tương thích.
3. Xác nhận minimum JDK của toàn bộ stack.
4. Chọn BOM/parent hoặc dependency management làm nguồn version chuẩn.
5. Chỉ ra module/service có ràng buộc không cho nâng đồng thời.

### Giai đoạn C — Chuyển source và cấu hình

1. Đổi các Enterprise imports trong phạm vi được xác nhận.
2. Nâng framework và third-party adapters.
3. Cập nhật web.xml, persistence.xml, validation.xml và descriptors đang dùng.
4. Nâng code generators, annotation processors và regenerate source.
5. Loại bản API/provider cũ khỏi graph khi không còn sử dụng.

### Giai đoạn D — Xác nhận liên kết runtime

1. Start ứng dụng trên JDK/container mục tiêu.
2. Kiểm tra Servlet routes, filters, listeners.
3. Bootstrap ORM, nhận entities, chạy database integration tests.
4. Thực thi Bean Validation qua request và service.
5. Kiểm tra transaction rollback, security và serialization.
6. Chạy contract tests với API consumers.

### Giai đoạn E — Triển khai và loại bỏ phần tương thích

1. Dùng staging gần production, có server/container đúng version.
2. Rollout từng bước nếu hệ thống có điều kiện.
3. Giám sát startup errors, HTTP 4xx/5xx, DB transactions và validation anomalies.
4. Giữ rollback plan xét cả schema, data và session serialization.
5. Chỉ loại bỏ adapter/nhánh cũ khi consumer và integration đã chuyển.

## 20. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách tiếp cận |
|---|---|---|
| Thay mọi javax thành jakarta. | Làm hỏng các package Java SE như javax.sql, javax.crypto. | Chỉ đổi Enterprise APIs thuộc phạm vi chuyển namespace. |
| Chỉ sửa import servlet. | WAR chạy trên container cũ, filters không nạp được. | Nâng container và third-party servlet integrations. |
| Chỉ thêm jakarta.persistence-api. | ORM provider cũ không nhận entity hoặc bootstrap lỗi. | Đồng bộ JPA provider, framework, metadata và transaction. |
| Chỉ thêm jakarta.validation-api. | Constraint annotation tồn tại nhưng không được thực thi. | Cung cấp provider và kích hoạt validation integration. |
| Trộn version tùy ý. | LinkageError, startup error, transaction behavior lệch. | Sử dụng BOM/compatibility matrix và kiểm thử. |
| Đóng gói Servlet API cùng external container không kiểm soát. | Duplicate class/provider và classloading conflicts. | Dùng provided/compile-only nếu server cung cấp đúng API. |
| Để generated code javax trong project Jakarta. | Compile/runtime mismatch và provider discovery sai. | Nâng generator, regenerate và kiểm tra output. |
| Bỏ qua XML descriptors. | Scanner/metadata dùng namespace cũ. | Kiểm tra web.xml, persistence.xml, validation.xml, orm.xml. |
| Coi @Transactional cùng tên là tương đương. | Sai rollback semantics hoặc không có interceptor. | Xác nhận transaction manager và annotation integration. |
| Chỉ test CRUD thành công. | Bỏ qua lỗi rollback, constraints, lazy loading và tenant security. | Test success/failure paths xuyên các lớp. |
| Chỉ test qua mock controller. | Không phát hiện Filter/Servlet container/provider lỗi. | Chạy integration tests qua runtime thật. |
| Cho rằng có cả javax/jakarta jars nghĩa là tương thích. | Type/annotation binary names khác nhau. | Đặt boundary rõ và tránh trộn provider không kiểm soát. |

## 21. Checklist xác nhận migration

Đối với module Servlet/JPA/Validation có thể chuẩn bị:

- [ ] JDK mục tiêu và Java tối thiểu của framework đã được xác định.
- [ ] Jakarta EE platform/framework/container versions được đối chiếu.
- [ ] Servlet API và Servlet runtime cùng namespace và đúng specification.
- [ ] Tất cả filters/listeners/initializers có phiên bản Jakarta-compatible.
- [ ] JPA annotations, Persistence API và ORM provider cùng thế hệ.
- [ ] Database driver, transaction manager, persistence metadata được kiểm tra.
- [ ] Bean Validation API, provider, message interpolation và integration hoạt động.
- [ ] Custom validators, method validation, @Valid và constraint groups được test.
- [ ] CDI/injection/transaction/REST/JSON/WebSocket API nếu dùng được đồng bộ.
- [ ] Generated code và XML descriptors không còn tham chiếu sai thế hệ.
- [ ] Không xóa nhầm các package javax còn thuộc Java SE.
- [ ] Dependency graph và packaging/runtime scopes đã được xác minh.
- [ ] HTTP API contract tests bao gồm trường hợp lỗi, validation và security.
- [ ] JPA transaction, rollback, database constraint và lazy-loading tests đã chạy.
- [ ] Có kiểm thử qua container/runtime thật và theo dõi rollout.

Checklist là hướng dẫn cho một migration thực tế; các mục phải có bằng chứng từ build, test và deployment chứ không tự được coi là hoàn thành khi chỉ đọc tài liệu này.

## 22. Ví dụ tình huống tích hợp: ứng dụng quản lý khách hàng

Giả sử một ứng dụng cũ chạy:

~~~text
Java cũ
  └─ Servlet javax
      └─ DTO javax.validation
          └─ Service
              └─ JPA javax.persistence + ORM cũ
                  └─ Database
~~~

Sau migration, mục tiêu:

~~~text
JDK được hỗ trợ bởi stack mục tiêu
  └─ Jakarta Servlet container / MVC framework
      └─ DTO jakarta.validation + provider
          └─ Service + transaction integration
              └─ jakarta.persistence + ORM provider tương thích
                  └─ Database
~~~

Quy trình test:

**Trường hợp hợp lệ:** gửi một request tạo khách hàng có displayName/email hợp lệ; controller route hoạt động; validator không báo lỗi; service mở transaction; JPA persist; database commit; response trả ID và schema đúng như hợp đồng.

**Trường hợp DTO không hợp lệ:** thiếu displayName hoặc email sai; Bean Validation được gọi, response chứa lỗi phù hợp và database không tạo record.

**Trường hợp database reject:** đưa ra một tình huống vi phạm unique constraint trong môi trường test; exception được phân loại đúng, transaction rollback, dữ liệu không ở trạng thái nửa chừng.

**Trường hợp không có quyền:** user thuộc tenant A cố sửa khách hàng thuộc tenant B; server từ chối trước khi thao tác dữ liệu, không lộ thông tin ngoài phạm vi.

**Trường hợp runtime lệch thế hệ:** cố deploy thử artifact Jakarta lên container chỉ hỗ trợ javax trong môi trường thử nghiệm; xác nhận pipeline hoặc smoke test phát hiện không tương thích, thay vì chờ sự cố ở production.

Những kịch bản này cho thấy Servlet, Persistence và Validation chỉ thực sự được đồng bộ khi **đường request xuyên lớp** có hành vi nhất quán theo yêu cầu, bao gồm cả trường hợp thất bại.

## 23. Kết luận

Đồng bộ Servlet, JPA, Validation và các Jakarta APIs liên quan là công việc phối hợp **namespace, specification version, implementation/provider, framework/container, dependency graph, metadata và runtime behavior**. Việc đổi javax.servlet thành jakarta.servlet, javax.persistence thành jakarta.persistence hay javax.validation thành jakarta.validation là cần thiết ở những stack phù hợp, nhưng chưa đủ nếu provider, code generator, XML descriptor hoặc application server vẫn thuộc thế hệ cũ.

Một lộ trình an toàn bắt đầu từ inventory, lựa chọn platform/BOM nhất quán, xác định chủ thể cung cấp Servlet runtime, JPA provider, Bean Validation provider và transaction manager; sau đó nâng source/config/generated code, chạy integration tests trên JDK/container mục tiêu và kiểm chứng hợp đồng HTTP/dữ liệu/authorization.

**Mục tiêu không phải là loại bỏ mọi chuỗi javax khỏi repository, mà là bảo đảm từng API Java Enterprise được dùng đúng thế hệ, được thực thi bởi provider phù hợp và duy trì hành vi nghiệp vụ đã cam kết khi hệ thống chuyển sang Jakarta.**
