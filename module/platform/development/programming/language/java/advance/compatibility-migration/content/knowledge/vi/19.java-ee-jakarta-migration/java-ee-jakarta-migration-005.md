# Thay đổi dependency API, implementation và scope đóng gói

Khi di chuyển ứng dụng từ Java EE sang Jakarta EE hoặc nâng JDK, việc thay các dòng `import javax.*` thành `import jakarta.*` mới chỉ là một phần công việc. Một ứng dụng còn phải xác định **API nào dùng để biên dịch**, **implementation nào thực thi tại runtime**, **ai cung cấp implementation đó** và **thư viện nào thực sự được đóng gói vào JAR/WAR/EAR**. Cấu hình sai ở một trong bốn lớp này có thể dẫn tới tình huống rất khó hiểu: IDE compile thành công nhưng WAR triển khai thất bại, unit test chạy được nhưng production thiếu provider, hoặc ứng dụng chứa hai bản API xung đột với application server.

Trong bối cảnh *Java Advance Compatibility Migration*, điều quan trọng là không chọn scope theo thói quen. Scope phụ thuộc vào **mô hình triển khai**: Jakarta EE application server đầy đủ, servlet container, Spring Boot executable JAR/WAR, ứng dụng Java SE độc lập hoặc một module thư viện được tiêu thụ bởi hệ thống khác. Cùng một API như Jakarta Servlet có thể cần `provided` khi deploy lên server cung cấp nó, nhưng một executable JAR phải đem theo embedded servlet engine hoặc cơ chế runtime tương đương.

Bài này giải thích cách tách dependency API và implementation/provider, chọn scope Maven/Gradle, thay đổi từ `javax.*` sang `jakarta.*`, nhận diện duplicate class/provider, kiểm tra artifact cuối cùng và xây dựng chiến lược đóng gói có bằng chứng.

## 1. Bốn câu hỏi trước khi sửa dependency

Mỗi công nghệ Java EE/Jakarta EE mà ứng dụng sử dụng phải trả lời được:

1. **API nào?** Source code import interface, annotation hay class công khai từ artifact nào?
2. **Implementation nào?** Thư viện hoặc application server nào cung cấp code chạy thật và provider tương ứng?
3. **Ai sở hữu runtime?** Ứng dụng tự đóng gói implementation, hay container cung cấp và quản lý lifecycle?
4. **Scope nào?** Dependency cần trên compile classpath, runtime classpath, test classpath hay chỉ một số môi trường?

Ví dụ, khi code gọi:

```java
import jakarta.validation.Validation;
import jakarta.validation.Validator;

Validator validator = Validation
        .buildDefaultValidatorFactory()
        .getValidator();
```

`jakarta.validation-api` cung cấp API. Nhưng để `buildDefaultValidatorFactory()` tìm được implementation, runtime cần một provider Bean Validation tương thích — do server cung cấp hoặc được ứng dụng mang theo, ví dụ Hibernate Validator ở một stack phù hợp. Chỉ có API JAR thường không đủ.

Một ví dụ khác:

```java
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
```

Class `HttpServlet` thuộc Servlet API, nhưng code trên không tự tạo HTTP server. Một Jakarta EE server, servlet container hoặc embedded container/framework phải quản lý listener, request dispatch, session và servlet lifecycle.

**API có trên compile classpath không chứng minh implementation sẽ tồn tại khi deploy.**

## 2. Java EE và Jakarta EE: đổi namespace là thay đổi kiểu nhị phân

### 2.1. Từ `javax.*` sang `jakarta.*`

Java EE trước đây dùng nhiều package `javax.*`. Jakarta EE 8 vẫn giữ nhiều package `javax.*` để bảo toàn tương thích ở giai đoạn chuyển giao; **Jakarta EE 9** chuyển nhiều API doanh nghiệp sang namespace `jakarta.*`.

Ví dụ:

| Công nghệ | Package cũ | Package mới |
|---|---|---|
| Servlet | `javax.servlet.*` | `jakarta.servlet.*` |
| Persistence/JPA | `javax.persistence.*` | `jakarta.persistence.*` |
| Bean Validation | `javax.validation.*` | `jakarta.validation.*` |
| CDI | `javax.enterprise.*` | `jakarta.enterprise.*` |
| JAX-RS | `javax.ws.rs.*` | `jakarta.ws.rs.*` |
| JAXB | `javax.xml.bind.*` | `jakarta.xml.bind.*` |
| JAX-WS | `javax.xml.ws.*` | `jakarta.xml.ws.*` |
| Activation | `javax.activation.*` | `jakarta.activation.*` |
| Transaction/JTA | `javax.transaction.*` | `jakarta.transaction.*` |
| Common Annotations | `javax.annotation.*` | `jakarta.annotation.*` |

Tên đầy đủ `javax.servlet.http.HttpServlet` và `jakarta.servlet.http.HttpServlet` là **hai binary name khác nhau**. JVM không ánh xạ chúng cho nhau. Một framework đã được compile để tìm `jakarta.servlet.Filter` không thể tự động sử dụng một implementation chỉ triển khai `javax.servlet.Filter`.

Đổi namespace vì vậy là **thay đổi API/binary compatibility**, không phải thay đổi tên import mang tính thẩm mỹ.

### 2.2. Không đổi mọi `javax.*` một cách cơ học

Không phải tất cả package `javax.*` đều thuộc Java EE và chuyển sang Jakarta. Một số API Java SE vẫn ở tên cũ, ví dụ:

- `javax.net.ssl.*`.
- `javax.crypto.*`.
- `javax.xml.parsers.*`, `javax.xml.transform.*`.
- `javax.sql.*`.
- `javax.naming.*`.

Các API này cần được xem theo JDK/Java SE contract. Đổi toàn bộ `javax.` thành `jakarta.` bằng tìm-thay chuỗi sẽ gây lỗi và có thể phá code đang đúng.

### 2.3. Tên artifact chưa chắc cho biết package

Trong giai đoạn chuyển tiếp, một số artifact mang tên hoặc groupId có chữ `jakarta` nhưng version cũ vẫn chứa package `javax.*`. Không nên quyết định namespace chỉ từ tên Maven artifact.

Khi chọn phiên bản, phải kiểm tra:

- Tài liệu/version line của Jakarta EE specification và implementation.
- Class thực sự nằm trong JAR.
- Framework major version.
- Generated code và annotation.
- API mà server/runtime đã công bố hỗ trợ.

Một tổ hợp thường có ranh giới theo thế hệ: API JAXB/JAX-WS nhánh 2.x chủ yếu dùng `javax`, các nhánh mới hơn dùng `jakarta`. Tuy nhiên, ma trận version chính xác phải được xác nhận theo từng artifact cụ thể.

## 3. API, implementation, provider và container khác nhau ở đâu?

### 3.1. API artifact

API artifact chứa contract được developer dùng: interface, annotation, exception, type chung và đôi khi có các class factory/delegation.

Ví dụ:

```text
jakarta.servlet:jakarta.servlet-api
jakarta.persistence:jakarta.persistence-api
jakarta.validation:jakarta.validation-api
jakarta.ws.rs:jakarta.ws.rs-api
jakarta.enterprise:jakarta.enterprise.cdi-api
jakarta.xml.bind:jakarta.xml.bind-api
```

Những artifact này giúp code biên dịch nhưng không nhất thiết thực hiện toàn bộ contract.

### 3.2. Implementation artifact

Implementation cung cấp behavior thật. Một số ví dụ:

| Công nghệ | API | Runtime/implementation có thể gặp |
|---|---|---|
| Servlet | `jakarta.servlet-api` | Tomcat, Jetty, Undertow hoặc server Jakarta EE |
| Persistence | `jakarta.persistence-api` | Hibernate ORM, EclipseLink hoặc provider của server |
| Bean Validation | `jakarta.validation-api` | Hibernate Validator hoặc provider tương thích |
| JAX-RS | `jakarta.ws.rs-api` | Jersey, RESTEasy, Apache CXF hoặc server |
| CDI | `jakarta.enterprise.cdi-api` | Weld, OpenWebBeans hoặc server |
| JAXB | `jakarta.xml.bind-api` | GlassFish JAXB Runtime hoặc provider tương thích |
| JAX-WS | `jakarta.xml.ws-api` | Metro, CXF hoặc server |
| Activation | `jakarta.activation-api` | Angus Activation hoặc provider phù hợp |
| Transaction | `jakarta.transaction-api` | Transaction manager/runtime của container hoặc stack riêng |

Các implementation được nêu là ví dụ phổ biến, không có nghĩa chúng có thể hoán đổi không cần kiểm tra cấu hình. Một application server thường tích hợp cả provider lẫn lifecycle, transaction boundary và classloading policy.

### 3.3. Provider discovery

Một số API tìm implementation qua service-provider mechanism, cấu hình framework hoặc API factory. Ví dụ Bean Validation, JAXB, JAX-RS client/runtime và các stack Java EE khác có thể sử dụng provider discovery.

Nếu chỉ có API:

- Compiler vẫn nhận ra interface.
- Class loader có thể nạp được API class.
- Lỗi có thể chỉ xảy ra khi gọi factory hoặc khởi tạo service.

Dấu hiệu thường gặp là không tìm được provider, `ServiceConfigurationError`, `NoProviderFoundException`, `JAXBException` hoặc lỗi khởi tạo framework.

Ngược lại, nếu có **nhiều provider cạnh tranh**, behavior còn phụ thuộc cơ chế chọn provider, class loader, ServiceLoader metadata và cấu hình. Không mặc định “càng nhiều implementation càng an toàn”.

### 3.4. Container cung cấp cả API và behavior vận hành

Jakarta EE application server có thể cung cấp nhiều specification implementations, quản lý:

- Servlet lifecycle, request routing và threading.
- Dependency injection/CDI.
- Transaction, persistence context.
- JNDI resources và connection pool.
- Security, authentication/authorization.
- REST endpoint dispatch và validation.
- Messaging và các dịch vụ platform khác.

Một servlet container tối giản như Tomcat/Jetty **không đồng nghĩa** một full Jakarta EE application server. Nó thường cung cấp Servlet và một số công nghệ liên quan ở mức container được hỗ trợ, nhưng không mặc định cung cấp toàn bộ JPA, CDI, JAX-RS, EJB, messaging hoặc Bean Validation.

Vì thế cùng một `WAR` chạy trên full Jakarta EE server có thể cần phạm vi dependency khác WAR chạy trên servlet container.

## 4. Scope Maven: compile, provided, runtime, test

### 4.1. Scope điều khiển classpath và tính lan truyền

Maven cung cấp một số scope thông dụng:

| Scope | Compile classpath | Runtime classpath của project | Test classpath | Ý nghĩa khi đóng gói |
|---|---|---|---|---|
| `compile` (mặc định) | Có | Có | Có | Phụ thuộc ứng dụng cần và thường được đóng vào WAR nếu phù hợp |
| `provided` | Có | Không được Maven xem là runtime dependency chuẩn | Có | Dự kiến runtime/container cung cấp; không đưa vào `WEB-INF/lib` theo packaging WAR thông thường |
| `runtime` | Không trực tiếp cho main compilation | Có | Có | Thư viện chỉ cần khi chạy; thường vào WAR nếu phù hợp |
| `test` | Không cho main compilation | Không | Có | Chỉ cho test |
| `system` | Cơ chế legacy dựa vào đường dẫn local | Khó tái lập | Tùy ngữ cảnh | Nên tránh vì không quản lý artifact qua repository bình thường |
| `import` | Không phải dependency application | Không | Không | Chỉ dùng cho BOM loại `pom` trong `dependencyManagement` |

Cột “đóng gói” còn phụ thuộc plugin và packaging type. Ví dụ jar plugin tạo thin JAR mặc định không nhúng mọi dependency dù chúng có `compile`/`runtime` scope; WAR plugin thường đóng những dependency tương ứng vào `WEB-INF/lib`.

Không xem scope là một câu lệnh duy nhất buộc mọi packaging plugin trên thị trường hoạt động giống nhau.

### 4.2. Ví dụ Servlet API do container cung cấp

```xml
<dependencies>
    <dependency>
        <groupId>jakarta.servlet</groupId>
        <artifactId>jakarta.servlet-api</artifactId>
        <version>${servlet.api.version}</version>
        <scope>provided</scope>
    </dependency>
</dependencies>
```

Đây là trường hợp điển hình nếu WAR được triển khai lên server/container **thực sự cung cấp Jakarta Servlet API cùng thế hệ**.

Ý nghĩa:

1. Source compile được với `HttpServlet`.
2. Test classpath có thể có API theo Maven scope.
3. Artifact WAR không cần và thường không nên mang bản Servlet API riêng.
4. Runtime server phải cung cấp API/implementation tương ứng.

Nếu deploy WAR lên container còn dùng `javax.servlet.*` thì scope `provided` không làm Jakarta API xuất hiện. Ứng dụng sẽ không tương thích với container đích và có thể không deploy được.

### 4.3. API cần compile, implementation do ứng dụng đóng gói

Giả sử ứng dụng Java SE muốn dùng JAXB Jakarta:

```xml
<dependencies>
    <dependency>
        <groupId>jakarta.xml.bind</groupId>
        <artifactId>jakarta.xml.bind-api</artifactId>
        <version>${jaxb.api.version}</version>
    </dependency>

    <dependency>
        <groupId>org.glassfish.jaxb</groupId>
        <artifactId>jaxb-runtime</artifactId>
        <version>${jaxb.runtime.version}</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

API nằm ở compile/runtime của ứng dụng; runtime provider được khai báo ở `runtime` nếu code không trực tiếp gọi API implementation. Nhưng thin JAR mặc định vẫn cần cơ chế đưa cả hai vào runtime classpath, ví dụ distribution, lib directory, container image hoặc packaging plugin.

Các version placeholder phải được chọn theo thế hệ `jakarta` tương thích và theo vendor/platform BOM của dự án. Không chọn tùy tiện một version API và một version runtime rồi mặc định là hợp lệ.

### 4.4. Optional không thay thế provided

Maven `<optional>true</optional>` thường dùng để hạn chế một dependency được truyền tự động tới consumer khác. Nó **không tương đương** `provided` và không có nghĩa application runtime sẽ cung cấp dependency đó.

Nếu một thư viện dùng một driver/protocol tùy chọn, optional có thể phù hợp ở module thư viện; còn ứng dụng thực thi vẫn phải khai báo module mà nó chọn. Nếu server cung cấp API, `provided` mới phản ánh ý định compile-only ở packaging ứng dụng kiểu truyền thống.

## 5. Scope Gradle: implementation, compileOnly, runtimeOnly và provided

### 5.1. Configuration cơ bản

Trong project Java hoặc Java Library:

| Gradle configuration | Main compile | Main runtime | Ý nghĩa điển hình |
|---|---|---|---|
| `implementation` | Có | Có | Dependency nội bộ mà project dùng cả compile/runtime |
| `api` với `java-library` | Có | Có | Dependency xuất hiện trong public API cho consumer compilation |
| `compileOnly` | Có | Không | API chỉ cần để compile, runtime được nơi khác cung cấp |
| `runtimeOnly` | Không | Có | Provider/driver/plugin runtime không gọi trực tiếp từ source |
| `testImplementation` | Test compilation | Test runtime | Dependency dành cho test |
| `testRuntimeOnly` | Không phải test compilation dependency | Test runtime | Test engine/provider chỉ cần khi chạy test |

Tùy plugin và version Gradle, còn có những configuration khác. Không nên chuyển scope Maven sang Gradle bằng cách thay tên chữ một cách máy móc mà chưa xem packaging và publication.

### 5.2. Gradle WAR và provided configurations

Khi áp dụng `war` plugin, Gradle có các configuration đặc thù như `providedCompile` và `providedRuntime` để biểu đạt dependency được container cung cấp khi WAR triển khai.

Ví dụ Groovy DSL:

```groovy
plugins {
    id "war"
}

dependencies {
    providedCompile(
        "jakarta.servlet:jakarta.servlet-api:${servletApiVersion}"
    )

    implementation(
        "org.glassfish.jersey.containers:jersey-container-servlet:${jerseyVersion}"
    )
}
```

Ví dụ này minh họa **WAR triển khai lên servlet container Jakarta tương thích**: container cung cấp Servlet API, còn ứng dụng mang theo Jersey/JAX-RS implementation nếu container không cung cấp JAX-RS. Cần kiểm tra dependencies bắc cầu và các module Jersey bắt buộc của stack cụ thể.

Không dùng ví dụ này làm cấu hình cố định cho full Jakarta EE server có JAX-RS provider riêng. Nếu server cung cấp JAX-RS, việc đóng thêm Jersey có thể tạo provider conflict hoặc behavior khác.

### 5.3. compileOnly và test classpath

Ví dụ:

```groovy
plugins {
    id "java"
}

dependencies {
    compileOnly(
        "jakarta.servlet:jakarta.servlet-api:${servletApiVersion}"
    )
}
```

`compileOnly` không có nghĩa API tự xuất hiện trong test compilation/runtime configurations ở mọi setup. Nếu test cần truy cập trực tiếp các type đó hoặc khởi tạo servlet container, cấu hình riêng test dependencies/test runtime phù hợp.

Ví dụ test khởi chạy embedded servlet container cần một implementation để chạy, không chỉ Servlet API. Ngược lại, test unit dùng mock request/response có thể chỉ cần API và mock library.

### 5.4. api và public signatures của reusable library

Trong `java-library` plugin, `api` giúp consumer compile nhìn thấy dependencies mà public API của thư viện phơi bày. Nhưng việc dùng `api` với Jakarta API có thể còn kéo runtime dependency theo mô hình dependency metadata.

Nếu thư viện chỉ cần API để compile và muốn consumer phải tự chọn container, cần thiết kế publication metadata phù hợp. Các Gradle version hỗ trợ `compileOnlyApi` cho use case “API lộ trong public signature nhưng không được cung cấp ở runtime”. Đây là cơ chế hữu ích khi được hỗ trợ, nhưng cần kiểm tra publication và consumer Maven/Gradle thực tế.

Không nên chọn `implementation`, `api` hay `compileOnly` chỉ theo cách làm code compile. Hãy xét liệu consumer có cần type đó tại compile time, runtime do ai cung cấp và metadata được publish có truyền đúng ý định hay không.

### 5.5. Phân biệt BOM/platform với scope

Gradle:

```groovy
dependencies {
    implementation platform(
        "com.example.platform:example-dependencies:1.0.0"
    )

    implementation "com.example:example-client"
}
```

Platform quản lý constraints/version; nó **không tự quyết định** dependency nên nằm ở `compileOnly`, `runtimeOnly` hay `providedCompile`. Tương tự Maven `dependencyManagement` không tự đóng gói implementation.

Để quản lý đúng Java EE/Jakarta dependency, phải quyết định đồng thời **version family** và **scope theo mô hình triển khai**.

## 6. Mô hình A: WAR/EAR trên Jakarta EE application server

### 6.1. Server là bên sở hữu các API/implementation thuộc platform

Giả sử ứng dụng được triển khai vào một Jakarta EE server đã được kiểm chứng hỗ trợ profile/specification version phù hợp. Server có thể cung cấp Servlet, CDI, JPA, JTA, Bean Validation, JAX-RS hoặc các capability khác theo profile và cấu hình.

Khi đó, application có thể compile bằng platform API và **không đóng gói các API/platform implementations do server cung cấp**.

Maven:

```xml
<packaging>war</packaging>

<dependencies>
    <dependency>
        <groupId>jakarta.platform</groupId>
        <artifactId>jakarta.jakartaee-api</artifactId>
        <version>${jakarta.ee.version}</version>
        <scope>provided</scope>
    </dependency>
</dependencies>
```

Đây là ví dụ tổng quát cho ứng dụng mục tiêu là Jakarta EE server tương thích. Tránh chỉ khai báo umbrella API nếu ứng dụng chỉ dùng một tập specification nhỏ, hoặc nếu server thực tế chỉ hỗ trợ profile hẹp hơn. Compile được với toàn bộ API không chứng minh server cung cấp toàn bộ API đó.

### 6.2. Không đóng gói provider trùng với server khi chưa có chủ đích

Ví dụ server đã cung cấp JPA provider và transaction manager. Nếu ứng dụng lại thêm `hibernate-core`, một JPA API JAR khác và transaction implementation vào `WEB-INF/lib`, các rủi ro gồm:

- Hai provider hoặc hai phiên bản API trên các class loader khác nhau.
- Server chọn provider không như ứng dụng mong muốn.
- Provider của ứng dụng không tích hợp đúng transaction/data source do server quản lý.
- Lỗi `ClassCastException`, `LinkageError` hoặc `NoSuchMethodError`.
- Behavior persistence context/lazy loading khác baseline.

Không có quy tắc tuyệt đối “mọi implementation trong WAR đều sai”: một số server cho phép ứng dụng dùng provider riêng nếu cấu hình classloading và integration phù hợp. Nhưng đây phải là quyết định có tài liệu, không phải hệ quả vô tình từ dependency graph.

### 6.3. Kiểm tra server profile thật

“Jakarta EE compatible” là khái niệm có version/profile. Một server hỗ trợ Web Profile hoặc tập specification cụ thể có thể không cung cấp đủ toàn bộ full-platform APIs. Cần kiểm tra:

- Server vendor/version.
- Jakarta EE platform/profile version.
- Servlet/JPA/CDI/Validation/JAX-RS spec level.
- Provider thực tế, classloading policy, deployment descriptors.
- Cấu hình resource như data source, transaction manager và security.

Nếu ứng dụng compile bằng một Jakarta EE API thế hệ mới hơn server, dùng `provided` chỉ che thiếu dependency trên build chứ không sửa được mismatch tại deployment.

## 7. Mô hình B: WAR trên servlet container

### 7.1. Servlet container không phải full Jakarta EE platform

Ví dụ một ứng dụng triển khai lên Tomcat hoặc Jetty thế hệ Jakarta. Container có thể cung cấp Servlet API và engine, nhưng không tự cung cấp đầy đủ CDI/JPA/JAX-RS/Bean Validation tùy sản phẩm/version.

Ứng dụng muốn JAX-RS hoặc JPA có thể cần đóng gói implementation tương ứng.

Maven minh họa:

```xml
<packaging>war</packaging>

<dependencies>
    <!-- Container cung cấp Servlet API -->
    <dependency>
        <groupId>jakarta.servlet</groupId>
        <artifactId>jakarta.servlet-api</artifactId>
        <version>${servlet.api.version}</version>
        <scope>provided</scope>
    </dependency>

    <!-- Ví dụ ứng dụng tự mang JAX-RS runtime -->
    <dependency>
        <groupId>org.glassfish.jersey.containers</groupId>
        <artifactId>jersey-container-servlet</artifactId>
        <version>${jersey.version}</version>
    </dependency>
</dependencies>
```

Jersey version và các module đi kèm phải đúng với Servlet version/container. Nếu thư viện JAX-RS có dependency bắc cầu tới Servlet API, cần xem packaged WAR để tránh API không cần thiết hoặc xung đột.

### 7.2. Chọn scope dựa vào owner của từng service

| Công nghệ | Servlet container thường cung cấp? | Nếu ứng dụng cần |
|---|---|---|
| Servlet API/engine | Có, theo version container | API `provided`; không đóng thêm servlet engine trùng |
| JPA provider | Không mặc định | Tự đóng provider/đưa runtime dịch vụ bên ngoài |
| CDI | Không mặc định | Chọn CDI implementation và integration |
| JAX-RS | Không mặc định | Chọn Jersey/RESTEasy/CXF hoặc framework |
| Bean Validation | Không mặc định | Chọn provider và dependency phù hợp |
| JAXB/JAX-WS | Không mặc định chỉ vì là servlet container | Cung cấp API/runtime/tools tương ứng khi cần |
| JTA transaction manager | Không nhất thiết như full Jakarta EE server | Dùng stack transaction được framework hỗ trợ |

Đây là nguyên tắc tổng quát. Một distribution mở rộng servlet container hoặc một framework đi kèm có thể cung cấp thêm các công nghệ này; phải kiểm tra bộ runtime thật.

### 7.3. Lỗi thường gặp

WAR trên servlet container có `jakarta.persistence-api` nhưng không có Hibernate/EclipseLink provider. Code compile, nhưng tạo `EntityManagerFactory` thất bại. Đây không phải vấn đề “thiếu phiên bản API” mà là **thiếu implementation hoặc bootstrap configuration**.

Tương tự, có `jakarta.validation-api` nhưng thiếu Bean Validation provider có thể dẫn đến lỗi tìm provider. Cần thêm runtime implementation hoặc chuyển sang môi trường có provider tương ứng.

## 8. Mô hình C: Executable JAR với embedded runtime

### 8.1. Ứng dụng tự chịu trách nhiệm runtime

Một executable JAR kiểu Spring Boot hoặc framework embedded thường đóng gói servlet engine, JSON stack, validation, JPA provider và nhiều thư viện khác tùy starters/modules được chọn.

Với Spring Boot ứng dụng web chạy embedded, dependency điển hình:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

Version và dependency management được framework/parent/BOM phù hợp quản lý. Starter web thường mang theo embedded servlet runtime theo configuration mặc định của stack tương ứng.

Nếu developer chuyển Servlet engine/runtime dependency thành `provided` mà không có container bên ngoài, executable JAR có thể thiếu class khi chạy. Ngược lại, nếu cố đóng cả một standalone server và các thư viện server không tương thích vào JAR, classpath có thể xung đột.

### 8.2. Không lạm dụng umbrella Jakarta EE API

Một executable JAR không nên chỉ thêm `jakarta.jakartaee-api` với scope `compile` rồi kỳ vọng mọi công nghệ platform được cung cấp. Umbrella API không tạo CDI container, transaction manager, JPA provider hoặc SOAP runtime.

Cách phù hợp hơn là dùng **starter/module/provider được framework khuyến nghị** cho các capability thực tế, để framework quản lý tương thích giữa API và implementation.

### 8.3. WAR của framework có quy tắc packaging riêng

Một số framework có thể tạo executable WAR vừa chạy độc lập vừa deploy trên servlet container, dùng vùng thư viện đặc thù hoặc scope `providedRuntime` cho embedded server. Ví dụ trong Spring Boot Gradle WAR packaging, starter Tomcat có thể được cấu hình ở `providedRuntime` theo hướng dẫn của version framework.

Phải kiểm tra artifact thực tế và quy trình deployment mà framework hỗ trợ. Không suy diễn quy tắc từ WAR của servlet container truyền thống sang mọi loại executable WAR.

## 9. Mô hình D: Java SE application, batch job và CLI

### 9.1. Không có Jakarta EE container ngầm định

Một CLI hoặc batch service chạy bằng:

```bash
java -jar migration-tool.jar
```

không tự có CDI, Bean Validation, JPA, JAXB hay JAX-WS runtime trừ khi được đóng gói hoặc cấp trên classpath/module path.

Ví dụ một công cụ dữ liệu dùng JAXB:

```xml
<dependencies>
    <dependency>
        <groupId>jakarta.xml.bind</groupId>
        <artifactId>jakarta.xml.bind-api</artifactId>
        <version>${jaxb.api.version}</version>
    </dependency>
    <dependency>
        <groupId>org.glassfish.jaxb</groupId>
        <artifactId>jaxb-runtime</artifactId>
        <version>${jaxb.runtime.version}</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Nếu tạo thin JAR, cần distribution/lib directory, classpath launcher hoặc packaging mechanism để runtime tìm được cả API và provider. Chỉ `mvn package` tạo JAR không mặc nhiên nhúng các dependency vào trong JAR.

### 9.2. JDK 11 đã loại bỏ một số API từng có sẵn

JEP 320 loại bỏ các module Java EE/CORBA được bundled trong JDK, gồm JAXB, JAX-WS, Activation và một số công cụ liên quan, từ **JDK 11**. Khi nâng JDK 8 lên 17/21, ứng dụng từng dựa vào chúng từ JDK phải tự quản lý các dependency bên ngoài.

Tuy nhiên, đừng coi mọi Jakarta API đều từng đi kèm JDK. Servlet, CDI, JPA và JAX-RS không phải các dịch vụ mà mọi JDK Java SE luôn tự cung cấp.

Các lỗi như:

```text
package javax.xml.bind does not exist
NoClassDefFoundError: javax/activation/DataHandler
```

cần được phân loại: thiếu API trên compile classpath, thiếu implementation/runtime, hay namespace mismatch. Thêm một API JAR bất kỳ không giải quyết được tất cả.

## 10. Scope cho reusable library khác scope của application

### 10.1. Public API có chứa Jakarta type

Giả sử một SDK dùng chung khai báo:

```java
package com.example.sdk;

public interface RequestCustomizer {
    void customize(jakarta.servlet.http.HttpServletRequest request);
}
```

Consumer compile source sử dụng `RequestCustomizer` có thể cần truy cập `HttpServletRequest` để hiểu signature. Nếu SDK dùng Maven `provided` cho Servlet API, dependency đó không được truyền như một runtime/compile dependency thông thường tới mọi consumer. Consumer cần tự khai báo API phù hợp hoặc thông qua platform/framework của họ.

Nếu Gradle library dùng `compileOnly`, type thường không được công bố như API dependency tự động cho consumer. Với các Gradle release hỗ trợ, `compileOnlyApi` có thể phù hợp hơn cho compile-time public surface không nên đưa vào runtime, nhưng cần kiểm chứng publication metadata và consumer thực tế.

### 10.2. Không ép consumer mang provider của SDK

Một SDK chỉ công bố interface JPA/JAX-RS không nên vô thức buộc mọi consumer dùng một implementation cụ thể nếu kiến trúc dự kiến để application server quyết định provider.

Ngược lại, nếu SDK thực hiện serialization qua một provider bắt buộc thì cần công bố rõ runtime dependency và điều kiện hỗ trợ. Sự khác biệt nằm ở contract của SDK, không chỉ tên artifact.

### 10.3. API compile compatibility không thay thế runtime contract

Giả sử SDK compile với Jakarta EE 10 API nhưng một consumer deploy trên server có Jakarta EE version thấp hơn. SDK vẫn có thể được publish thành công; lỗi phát sinh khi consumer compile/deploy.

Library publisher cần ghi:

- JDK tối thiểu và class-file target.
- Jakarta API/specification level được yêu cầu.
- Dependency scope được publish.
- Những API implementation nào do consumer/container phải cấp.
- Ma trận server/framework đã kiểm thử.
- Tính tương thích `javax`/`jakarta` và hạn chế hiện tại.

## 11. Thay đổi scope có thể phá ứng dụng dù version không đổi

### 11.1. Từ compile sang provided

Đổi Maven dependency:

```xml
<scope>compile</scope>
```

sang:

```xml
<scope>provided</scope>
```

có thể giúp tránh đóng Servlet API vào WAR khi server đã cung cấp nó. Nhưng nếu cùng artifact được chạy như standalone Java application, runtime sẽ không có dependency đó trừ khi có cách cung cấp khác.

**Thay đổi scope là thay đổi triển khai**, không chỉ cleanup POM.

### 11.2. Từ provided sang compile

Chuyển sang `compile` có thể làm WAR bắt đầu mang theo API/implementation do server vốn đã cung cấp. Trên một số server, đây là nguyên nhân gây xung đột class loader hoặc provider.

Lệnh build có thể pass vì project classpath đầy đủ, nhưng server deployment mới bộc lộ lỗi. Cần kiểm tra WAR contents trước/sau.

### 11.3. Chỉ có runtime provider nhưng thiếu compile API

Nếu source gọi trực tiếp API nhưng dependency chỉ ở `runtime`/`runtimeOnly` và không có API từ nơi khác, compiler có thể báo không tìm thấy package. Phải có API trên compile classpath (qua direct dependency hoặc một dependency khác được phép) và provider ở runtime.

### 11.4. Chỉ có compile API nhưng thiếu runtime provider

Đây là trường hợp Java EE/Jakarta thường gặp nhất khi chuyển từ full server sang servlet container hoặc CLI. Code compile nhưng factory khởi tạo thất bại. Phương án sửa là xác định runtime owner và cung cấp implementation tương thích, không chỉ thay version API.

## 12. Class loading và duplicate classes trong server

### 12.1. Container classloader khác application classloader

Trong WAR/EAR, server thường có class loader để cung cấp platform API và implementation; ứng dụng có class loader để nạp `WEB-INF/classes` và `WEB-INF/lib`. Quy tắc ưu tiên và isolation phụ thuộc server/version/config.

Nếu cùng một class hoặc package có mặt ở nhiều nơi, có thể gặp:

- API được nạp từ server, provider từ application.
- Một library provider được compile với API version khác.
- Hai class cùng binary name được định nghĩa bởi class loader khác nhau.
- Method signatures/type identity không khớp.
- SPI/provider registration thấy class không thể cast sang interface đang dùng.

Trong JVM, **class identity gồm binary name và defining class loader**. Cùng tên class nhưng khác defining loader không mặc nhiên là cùng kiểu.

### 12.2. Đừng chỉ nhìn dependency tree

Build tool chỉ biết graph mà nó resolve. Nó không nhất thiết biết các JAR được server đặt trong global library folder, domain configuration, shared lib directory hoặc một class loader riêng.

Vì vậy cần kiểm tra:

1. Dependency tree/build graph.
2. File thực tế trong WAR/JAR/EAR.
3. JAR/module do server cung cấp.
4. Class loader policy của server.
5. Runtime class-loading source khi cần.

Trên các JDK hiện đại, có thể dùng JVM class-loading logs trong môi trường phù hợp, ví dụ:

```bash
java -Xlog:class+load=info -jar app.jar
```

Với server, cần cấu hình JVM logging qua cơ chế startup được server hỗ trợ. Log có thể rất lớn, nên chỉ dùng trong phiên điều tra có kiểm soát.

### 12.3. Lỗi linkage khác lỗi dependency resolution

- `ClassNotFoundException`: thường xuất hiện khi code/framework cố nạp class theo tên mà không tìm được.
- `NoClassDefFoundError`: JVM cần một class tại runtime nhưng class không có/không thể được nạp theo yêu cầu.
- `NoSuchMethodError`: runtime class không có method descriptor mà bytecode caller yêu cầu.
- `AbstractMethodError`: implementation không đáp ứng method được yêu cầu tại dispatch.
- `ClassCastException`: object không thuộc type mà code đang cast, bao gồm khác classloader.
- `ServiceConfigurationError`: provider discovery/khởi tạo không phù hợp.
- `IllegalAccessError` hoặc lỗi module access: class/member không thể được truy cập theo runtime contract.

Những lỗi này không chứng minh chính xác “thiếu JAR X” chỉ dựa vào message. Phải truy ngược dependency version, binary name, classloader và thời điểm lỗi.

## 13. Kiểm tra artifact: WAR, JAR và EAR có gì bên trong?

### 13.1. WAR truyền thống

Một WAR thường có cấu trúc:

```text
application.war
├── WEB-INF/
│   ├── classes/
│   ├── lib/
│   │   ├── application-library.jar
│   │   └── provider-runtime.jar
│   └── web.xml       (nếu sử dụng)
└── ...
```

Với WAR triển khai lên server, cần biết dependency nào nên có và dependency nào **không nên** có trong `WEB-INF/lib`.

Ví dụ Servlet API do container cung cấp thường không cần nằm ở đó. Một JPA provider do ứng dụng lựa chọn có thể cần nằm ở đó nếu container không cung cấp, nhưng phải quản lý thêm các dependency và integration yêu cầu.

### 13.2. Kiểm tra bằng công cụ archive

Lệnh tham khảo:

```bash
jar tf build/libs/application.war
jar tf target/application.war

jar tf target/application.war | grep "WEB-INF/lib"
```

Trên Windows PowerShell có thể dùng `Select-String` thay `grep`. Những lệnh này chỉ minh họa workflow; tên artifact phải lấy từ build thực tế.

Kiểm tra tối thiểu:

- Có các runtime provider mà ứng dụng cần đóng gói.
- Không mang API/provider trùng với server ngoài chủ đích.
- Không có bản version khác nhau của cùng họ library gây conflict.
- Có `META-INF/services` hoặc service metadata cần cho provider.
- Generated classes, resources và deployment descriptors đầy đủ.
- Không có thư viện hoặc tool chỉ dành cho test/build trong production artifact.

### 13.3. Thin JAR và fat JAR

Maven jar plugin tạo JAR thường không nhúng toàn bộ transitive runtime dependencies. Một fat JAR/uber-JAR hoặc executable JAR do framework/plugin tạo có thể gom chúng thành một artifact, nhưng cấu trúc nội bộ tùy plugin.

Nếu chuyển từ launch command có classpath nhiều JAR sang `java -jar`, cần xác nhận provider và các library được tìm thấy. Không có cùng scope nghĩa là mọi packaging mode đều thu được cùng runtime graph.

### 13.4. Shading và ServiceLoader

Shading có thể hợp nhất/relocate class nhưng làm mất file `META-INF/services` nếu plugin không merge đúng. Khi đó API/implementation JAR có mặt nhưng provider discovery vẫn thất bại.

Không tùy tiện relocate `jakarta.*` hoặc `javax.*` API packages để “tránh xung đột”: framework và container sẽ tìm đúng binary names chuẩn. Một bản API đã relocate không còn là contract mà platform mong đợi.

## 14. BOM, platform và ma trận phiên bản không quyết định scope

### 14.1. BOM quản lý version, không tự thêm runtime

Ví dụ Maven:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example.platform</groupId>
            <artifactId>example-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

BOM thường quản lý version cho dependency theo quy tắc Maven. Nó không tự làm `jakarta.validation-api` hoặc provider Bean Validation được đưa vào runtime; ứng dụng vẫn cần khai báo dependency và scope đúng.

### 14.2. Gradle platform cũng vậy

```groovy
dependencies {
    implementation platform(
        "com.example.platform:example-bom:1.0.0"
    )

    compileOnly "jakarta.servlet:jakarta.servlet-api"
}
```

Platform cung cấp version constraints nếu BOM quản lý module đó, nhưng không biến `compileOnly` thành runtime dependency. Cần bảo đảm version có sẵn qua platform/constraint hoặc khai báo tường minh. Artifact `example-bom` ở đây chỉ là ví dụ giả định.

### 14.3. Chọn bộ phiên bản được framework hỗ trợ

Một hệ thống có thể phải đồng bộ:

- Jakarta Servlet API và container.
- JPA API/provider/transaction integration.
- Bean Validation API/provider và expression language dependency nếu cần.
- JAX-RS API/runtime.
- JAXB/JAX-WS/Activation API/runtime/tools.
- CDI API/implementation và extension.
- Spring/Jakarta EE/framework versions.
- JDK tối thiểu và class-file target.

Version numbers không nhất thiết giống nhau; điều cần là **ma trận tương thích được vendor/framework hỗ trợ và đã được kiểm chứng**.

## 15. Cách migrate từ javax sang jakarta ở lớp dependency

### 15.1. Chụp baseline thật

Trước khi thay đổi:

- Ghi JDK vendor/version, build tool và framework.
- Ghi runtime owner: full Jakarta EE server, servlet container hay embedded.
- Lưu Maven/Gradle dependency tree, plugin versions và artifact contents.
- Lưu application server version/profile.
- Kiểm kê generated source và compile-time annotations.
- Lưu contract integration tests và lỗi runtime hiện có.

Không dùng việc build success trên IDE làm baseline duy nhất.

### 15.2. Chọn đích trước khi sửa namespace

Có ba tình huống phổ biến:

**Tình huống 1 — Giữ Java EE/Javax:** Nâng JDK nhưng giữ framework/container thế hệ `javax.*` được hỗ trợ. Cần dùng API/implementation tương thích `javax`; với JAXB/JAX-WS/Activation trên JDK 11+, cung cấp dependency bên ngoài nếu cần.

**Tình huống 2 — Chuyển toàn bộ sang Jakarta:** Nâng container/framework/runtime và dependency sang thế hệ `jakarta.*`. Source, generated source, annotation, config và các extension phải được chuyển đồng bộ.

**Tình huống 3 — Hai hệ cùng tồn tại có chủ đích:** Một vài module/integration còn phụ thuộc `javax` trong khi phần mới dùng `jakarta`. Cần ranh giới rõ, adapter hoặc tách tiến trình/module; không giả định hai hệ implement cùng interface.

### 15.3. Kiểm kê source và API signature

Tìm:

```text
javax.servlet
javax.persistence
javax.validation
javax.ws.rs
javax.enterprise
javax.xml.bind
javax.xml.ws
javax.activation
javax.transaction
javax.annotation
```

Đồng thời tìm `jakarta.*` và kiểm tra nơi hai hệ đang trộn. Rà soát public method signatures, generated bytecode, annotation processor, ORM metadata và resource/service configuration.

### 15.4. Nâng runtime owner trước khi quyết định provided

Nếu deployment target vẫn là một servlet container `javax.servlet`, việc đổi source sang `jakarta.servlet` và đặt scope `provided` sẽ không thể tạo ra container Jakarta tương ứng. Container phải được nâng lên version tương thích hoặc chọn kế hoạch migration khác.

Ngược lại, nếu ứng dụng trở thành executable JAR có embedded runtime, một API trước đây `provided` có thể cần được mang theo qua framework starter/runtime dependency mới.

**Scope phải phản ánh hạ tầng sau migration**, không phản ánh hạ tầng cũ.

### 15.5. Thay API và implementation theo bộ

Ví dụ JPA:

- Đổi `javax.persistence.*` sang `jakarta.persistence.*` khi framework target yêu cầu.
- Dùng `jakarta.persistence-api` đúng thế hệ.
- Chọn Hibernate/EclipseLink provider tương thích.
- Đảm bảo transaction/connection pool integration.
- Chạy DDL/mapping/lazy loading và transaction tests.

Ví dụ Bean Validation:

- Dùng `jakarta.validation-api` cùng provider phù hợp.
- Cập nhật annotation `@NotNull`/`@Valid` đúng namespace.
- Kiểm tra validation interception và error mapping.
- Kiểm tra provider discovery và các extension liên quan.

Ví dụ JAX-RS:

- Dùng `jakarta.ws.rs-api`.
- Có container/provider JAX-RS tương thích.
- Kiểm tra resource registration, filters/interceptors và serializer.
- Chạy HTTP contract tests trên deployment thật.

### 15.6. Kiểm tra version và scope ở từng module

Một module test có thể dùng API `jakarta` nhưng production artifact còn đóng một JAR `javax` từ thư viện transitive. Một module thư viện có thể giấu provider dependency ở scope test nên unit tests pass còn consumer runtime fail.

Cần xem từng compile/runtime/test configuration và cách package cuối được tạo, không chỉ POM/Gradle build file gốc.

## 16. Quy trình kiểm chứng Maven

### 16.1. Effective POM và dependency graph

Các lệnh tham khảo:

```bash
./mvnw -version
./mvnw help:effective-pom
./mvnw dependency:tree
./mvnw dependency:tree -Dscope=runtime
```

Từ output hãy ghi:

- API phiên bản nào đang được chọn?
- Scope là `compile`, `provided` hay `runtime`?
- Implementation/provider đến từ direct hay transitive dependency?
- BOM/parent nào quản lý version?
- Có dependency bị override/excluded không?
- Plugin WAR/JAR/shade sẽ đóng cái gì?

Không giả định mọi plugin `dependency:tree` version đều in scope/conflict giống nhau; cần ghi plugin version nếu báo cáo yêu cầu so sánh.

### 16.2. Kiểm tra WAR artifact

Sau khi build trên pipeline được cho phép, liệt kê WAR:

```bash
jar tf target/application.war
```

So với policy packaging:

- Servlet API do server cung cấp có mặt trong WAR không?
- JPA/CDI/Validation/JAX-RS provider có được đóng gói đúng không?
- Một số API Jakarta được đóng vào WAR có gây duplicate với server không?
- Library chỉ dành cho test có lọt vào production không?

Nếu tổ chức dùng EAR, kiểm tra cả `EAR/lib`, từng WAR module và classloading policy của server.

### 16.3. Phân biệt plugin scope

Maven `dependencyManagement` và project dependencies không quyết định trực tiếp dependencies của plugin realm. Compiler, code generator, test runner và packaging plugin cần version và plugin dependency riêng khi có yêu cầu.

Ví dụ lỗi plugin XML codegen không tìm được class khi chạy có thể nằm ở plugin realm, không phải ứng dụng thiếu implementation ở `WEB-INF/lib`.

## 17. Quy trình kiểm chứng Gradle

### 17.1. Kiểm tra configuration cụ thể

Lệnh tham khảo:

```bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath
./gradlew :app:dependencyInsight \
    --dependency jakarta.servlet-api \
    --configuration runtimeClasspath
```

Thay `:app` bằng module thực tế và dùng cú pháp shell phù hợp. Với WAR plugin, cần kiểm tra `providedCompile`/`providedRuntime` cùng output WAR. Với custom packaging, xem task/plugin config thay vì suy từ runtimeClasspath đơn lẻ.

### 17.2. Tìm dependency đang được chọn

`dependencyInsight` có thể cho biết lý do chọn version, constraint/platform và đường dependency. Nếu provider xuất hiện hai lần từ hai đường khác nhau nhưng cuối cùng Gradle chọn một module version, vẫn cần kiểm tra artifact cuối có bản nhúng/shaded hoặc server-provided khác không.

### 17.3. Đừng đánh đồng buildscript/plugin với application

Một plugin Gradle có thể phụ thuộc JAXB, validation hoặc HTTP library để **tạo source**. Điều đó không có nghĩa application runtime có dependency tương ứng. Ngược lại, app runtime provider không tự xuất hiện trong plugin classpath.

Build logic, annotation processor, test engine và application runtime là các graph khác nhau. Hãy quản lý scope cho từng graph có chủ đích.

## 18. Những lỗi migration thường gặp

| Triệu chứng | Khả năng nguyên nhân | Bước kiểm tra |
|---|---|---|
| `package jakarta.servlet does not exist` | Thiếu API trên compile classpath | Xem direct dependency, scope, BOM và project module |
| `ClassNotFoundException: jakarta.servlet...` | Chạy ngoài Jakarta servlet runtime hoặc package sai | Kiểm tra mô hình deployment và container version |
| Server báo không deploy được Servlet/Filter | WAR Jakarta chạy trên server còn `javax` hoặc descriptor không phù hợp | Kiểm tra container Jakarta generation |
| `NoProviderFoundException` của Bean Validation | Chỉ có API, thiếu provider hoặc provider discovery sai | Kiểm tra runtime implementation/JAR/service metadata |
| `JAXBException` không tìm runtime | API có mặt nhưng thiếu JAXB provider | Kiểm tra runtime graph và namespace |
| JPA không tạo được `EntityManagerFactory` | Thiếu provider hoặc config transaction/data source sai | Kiểm tra provider và container ownership |
| REST endpoint trả 404 sau deploy | JAX-RS provider/resource registration không hoạt động | Xem servlet/provider registration và scan |
| `NoSuchMethodError` trên Jakarta class | API/provider version lệch | Kiểm tra runtime class loading và resolved versions |
| `ClassCastException` giữa provider types | Class loader isolation hoặc khác thế hệ API | Xem defining class loaders và artifact sources |
| WAR chứa nhiều servlet API JAR | Scope sai hoặc transitive dependency | Xem `WEB-INF/lib` và exclusions |
| Test pass nhưng WAR fail | Test runtime có provider khác server | Test artifact thật trên target server |
| Executable JAR báo thiếu Servlet/JPA runtime | Dependency đã đặt `provided`/`compileOnly` sai | Kiểm tra embedded runtime packaging |
| `ServiceConfigurationError` | Provider/service descriptor sai hoặc bị shading mất | Xem `META-INF/services` và provider version |
| `UnsupportedClassVersionError` | Một dependency dùng class-file version cao hơn runtime | So sánh min JDK và target |
| `InaccessibleObjectException`/module access | Reflection/module policy không phù hợp | Kiểm tra JPMS, `opens` và framework version |

Bảng là gợi ý điều tra, không phải kết luận chắc chắn chỉ từ tên exception. Cần stack trace, dependency graph, classpath và server logs để xác định nguồn gốc.

## 19. Định nghĩa một compatibility matrix có ích

Một hệ thống nhiều module cần bảng rõ về **ai cung cấp API và implementation**, thay vì chỉ danh sách version.

| Thành phần | API namespace | API compile scope | Implementation owner | Đóng vào artifact? | Đích runtime |
|---|---|---|---|---|---|
| Servlet | `jakarta.servlet` | `provided` | Servlet container | Không đóng Servlet API/engine trùng | Jakarta servlet container |
| JAX-RS | `jakarta.ws.rs` | Theo API exposure | Ứng dụng (Jersey) | Có, nếu container không có | Servlet container |
| JPA | `jakarta.persistence` | Provided hoặc compile theo mô hình | Full EE server hoặc app/provider | Theo owner | Server/embedded |
| Bean Validation | `jakarta.validation` | Theo API exposure | Container hoặc app | Theo owner | Server/embedded |
| JAXB | `jakarta.xml.bind` | Compile | Ứng dụng | Có nếu standalone cần | Java SE CLI |
| Transaction | `jakarta.transaction` | Provided hoặc compile theo mô hình | Container/transaction framework | Theo owner | Server/embedded |

Giá trị trong bảng minh họa các mô hình khác nhau, không phải một deployment duy nhất. Với dự án thật, cần thêm artifact coordinates, version, server/framework version, owner và bằng chứng test.

### 19.1. Matrix theo environment

Scope build có thể giống nhau nhưng môi trường khác nhau:

| Environment | Runtime thực tế | Cần kiểm tra |
|---|---|---|
| Developer machine | IDE hoặc embedded test server | Không che thiếu provider production |
| Unit tests | Mock/provider test dependency | Test có dùng runtime khác production không |
| CI integration | Container/service mô phỏng | Version khớp production |
| Staging | Application server/servlet container | Artifact thật, classloader và resources |
| Production | Image/server do ops quản lý | Đúng vendor/update, profile và provider |
| Rollback | Runtime/artefact cũ | Dữ liệu/API có tương thích khi quay lui |

Một bài test chỉ dùng embedded container không chứng minh WAR sẽ chạy giống vậy trên full Jakarta EE server hoặc server vendor khác.

## 20. Regression tests cho API/provider và packaging

### 20.1. Compile và linkage tests

- Compile source viết tay và generated source.
- Xác nhận không trộn `javax` và `jakarta` ngoài ranh giới đã thiết kế.
- Chạy consumer binary cũ khi hệ thống công bố backward compatibility.
- Kiểm tra class-file target và min JDK.
- Đối chiếu API signatures của các thư viện plugin/extension.

### 20.2. Provider discovery tests

- Bean Validation: tạo `ValidatorFactory` và validate object thực.
- JPA: tạo persistence context, persist/query trong transaction.
- JAX-RS: đăng ký resource/filter và gọi endpoint.
- CDI: resolve/inject bean, kiểm tra scope và lifecycle.
- JAXB: marshal/unmarshal DTO và verify annotations.
- JAX-WS: gọi SOAP endpoint, kiểm tra WSDL/headers/attachments.
- Activation: xử lý MIME/DataHandler payload nếu ứng dụng sử dụng.

Chọn các test phù hợp với stack; không thêm một công nghệ chỉ vì nó có trong Jakarta EE.

### 20.3. Artifact deployment tests

Thực hiện trên đúng artifact sẽ deploy:

1. Build và lưu checksum.
2. Kiểm tra WAR/JAR/EAR contents.
3. Deploy vào target container/framework version.
4. Kiểm tra logs không có provider/classloading conflicts.
5. Gọi smoke endpoints và các luồng persistence/validation/security.
6. Ghi runtime class source khi cần điều tra.
7. Kiểm tra undeploy/redeploy và resource cleanup.

Nếu production dùng EAR với nhiều module, kiểm tra classloader isolation và shared libs ở mức EAR, không chỉ một WAR bên trong.

### 20.4. Failure-case tests

- Bỏ provider để xác minh lỗi được nhận biết rõ trong môi trường test.
- Thử API/provider version mismatch có kiểm soát để hiểu failure mode.
- Deploy lên container generation không phù hợp trong môi trường cách ly để xác nhận guardrail.
- Kiểm tra duplicate JAR/service metadata khi shading.
- Thử testcase migration session, transaction và long-lived state khi rolling deployment.

Không cố tình đưa cấu hình lỗi vào production chỉ để thu thập exception. Test âm tính nên chạy trong fixture/staging cách ly.

## 21. Chiến lược phát hành và rollback

### 21.1. Khi dependency scope thay đổi, artifact cũng thay đổi

Một migration có thể giữ nguyên code nhưng thay:

```text
jakarta.servlet-api: compile -> provided
```

Dẫn đến WAR giảm một API JAR; tốt nếu container cung cấp đúng version, nhưng lỗi nếu target không cung cấp.

Do đó, scope diff phải được review như **deployment change**. Lưu trước/sau:

- Resolved compile/runtime graphs.
- WAR/JAR/EAR contents.
- Runtime container profile.
- Classloader/provider decision.
- Integration test result.

### 21.2. Rolling deployment giữa javax và jakarta

Một hệ thống đổi container/framework sang Jakarta namespace có thể không deploy song song cùng một WAR cho cả server `javax` và server `jakarta`. Nếu cần blue-green/rolling, thường phải duy trì hai artifact hoặc hai deployment tracks theo contract, không dựa vào việc thay scope tự động làm chúng dùng chung được.

Hãy kiểm tra external API contracts, dữ liệu/session state, messaging và database schema khi hai phiên bản cùng tồn tại. Đổi Java package nội bộ không nhất thiết đổi HTTP/JSON contract, nhưng có thể ảnh hưởng serialization/session replication/framework metadata.

### 21.3. Rollback yêu cầu hạ tầng tương ứng

Nếu nâng server từ thế hệ `javax` sang `jakarta`, rollback chỉ thay WAR mới bằng WAR cũ trên cùng server có thể không khả thi. Kế hoạch rollback phải bao gồm image/server version hoặc một deployment track tương thích.

Không coi “có artifact cũ” là đủ nếu runtime environment đã thay đổi theo API generation mới.

## 22. Ví dụ xuyên suốt: từ WAR Java EE cũ sang Jakarta EE

Giả sử dự án ban đầu:

```text
JDK 8 / Java EE application server cũ
  ├── javax.servlet API: provided
  ├── javax.persistence API: provided
  ├── JPA provider: server-managed
  ├── Bean Validation provider: server-managed
  └── WAR: business classes + app-specific libraries
```

Mục tiêu: dùng JDK hiện đại và server hỗ trợ Jakarta namespace.

### 22.1. Bước 1: Kiểm kê dependency cũ

Kiểm tra POM:

```xml
<dependencies>
    <dependency>
        <groupId>javax.servlet</groupId>
        <artifactId>javax.servlet-api</artifactId>
        <version>${legacy.servlet.version}</version>
        <scope>provided</scope>
    </dependency>
</dependencies>
```

Tìm các annotation khác như `javax.persistence.Entity`, `javax.validation.Valid`, CDI injection, REST resources và generated source. Xác định JPA/Validation providers đang được server cung cấp.

### 22.2. Bước 2: Chốt server Jakarta và API version

Chọn target server/version được hỗ trợ bởi hạ tầng, xác minh Java runtime và Jakarta EE profile/specification level. Chỉ sau đó mới chốt API dependencies và scope.

Ví dụ dùng umbrella API:

```xml
<dependency>
    <groupId>jakarta.platform</groupId>
    <artifactId>jakarta.jakartaee-api</artifactId>
    <version>${jakarta.ee.version}</version>
    <scope>provided</scope>
</dependency>
```

Nếu ứng dụng chỉ dùng Servlet hoặc server không hỗ trợ full-platform set, chọn các API cụ thể theo contract thay vì umbrella quá rộng.

### 22.3. Bước 3: Chuyển source và extension

Ví dụ:

```java
// Cũ
import javax.persistence.Entity;
import javax.validation.constraints.NotNull;

// Mới
import jakarta.persistence.Entity;
import jakarta.validation.constraints.NotNull;
```

Không đặt cả hai import trong cùng class chỉ để làm ví dụ compile. Kiểm tra generated source, annotation processor, XML descriptors, persistence configuration, CDI extensions và ORM/Validation integration cùng thế hệ.

### 22.4. Bước 4: Chọn provider owner

Nếu target server quản lý JPA/Validation, dùng API ở compile/provided scope theo thiết kế, tránh mang provider application không chủ đích.

Nếu migrate sang servlet container chỉ có Servlet, phải bổ sung JPA/Validation implementations và transaction integration thích hợp. Đây là **thay đổi mô hình runtime**, không thể giải quyết bằng namespace rename đơn thuần.

### 22.5. Bước 5: Build và kiểm tra WAR

Đối chiếu `WEB-INF/lib` sau migration:

- Không có Servlet API trùng server.
- Có các app-specific providers được yêu cầu (nếu có).
- Không có đồng thời hai runtime implementation xung đột.
- Không có library chỉ phục vụ test/build.
- Service metadata, resources và framework descriptors chính xác.

### 22.6. Bước 6: Deploy và verify

Chạy smoke test, persistence transactions, Bean Validation, authentication, REST endpoints và integration test qua container thật. Ghi server logs và resolved dependency versions.

Kết quả mong đợi không chỉ là WAR deploy “thành công” mà là **API compile-time khớp với capability và provider runtime được cung cấp**.

## 23. Những ngộ nhận nên tránh

| Ngộ nhận | Thực tế |
|---|---|
| “Có Jakarta API JAR tức là có Jakarta EE server” | API chỉ công bố contract; cần implementation/container |
| “Đặt dependency là provided luôn tốt hơn” | Chỉ đúng khi runtime thật sự cung cấp dependency tương ứng |
| “WAR và executable JAR nên dùng cùng scope” | Packaging/runtime owner khác nhau |
| “Tomcat cung cấp toàn bộ Jakarta EE” | Servlet container không mặc định là full Jakarta EE platform |
| “Cứ mang mọi provider vào WEB-INF/lib cho chắc” | Có thể gây duplicate hoặc conflict với server |
| “Một BOM giải quyết cả version và scope” | BOM quản lý version; scope và provider owner phải quyết định riêng |
| “Maven optional bằng provided” | Hai semantics khác nhau |
| “Gradle implementation giống Maven provided” | `implementation` thường tham gia runtime graph |
| “Chuyển javax sang jakarta chỉ cần sửa import” | Binary names, annotations, implementation và server đều cần đồng bộ |
| “Cùng class name thì classloader nào cũng tương thích” | Class identity còn phụ thuộc defining class loader |
| “Unit test pass nghĩa production provider đủ” | Test dependencies có thể che thiếu runtime provider |
| “JDK mới tự có JAXB/JAX-WS” | Các module từng bundled đã bị loại khỏi JDK từ Java 11 |
| “Đóng fat JAR sẽ tránh mọi lỗi provider” | Shading có thể làm mất SPI metadata hoặc tạo conflict |
| “Compile thành công đảm bảo WAR chạy được” | Phải deploy/test artifact với runtime owner thật |

## 24. Hồ sơ bàn giao cho một thay đổi dependency scope

Trước khi chốt migration, chuẩn bị:

1. **Deployment model:** full Jakarta EE server, servlet container, executable JAR/WAR hay Java SE CLI.
2. **Target matrix:** JDK runtime, framework, server/profile, API namespace/specification version.
3. **Dependency inventory:** group/artifact/version, direct/transitive, compile/runtime/test scope.
4. **Ownership matrix:** công nghệ nào do server cung cấp và công nghệ nào application đóng gói.
5. **API/implementation pairing:** provider/version và module nào thực thi.
6. **Namespace migration diff:** `javax.*`/`jakarta.*` trong code, generated source và dependencies.
7. **Artifact report:** danh sách `WEB-INF/lib` hoặc runtime contents của JAR/EAR.
8. **Classloading evidence:** nguồn class, providers, conflict resolution và module/server policies.
9. **Verification:** compile, provider discovery, integration, deployment, smoke và regression tests.
10. **Release and rollback plan:** hai môi trường có tương thích khi rolling deployment, artifact/runtime nào cần giữ.
11. **Security/supply-chain review:** dependency provenance, CVE, lockfile, SBOM và container hardening.
12. **Ownership:** người quản lý server runtime, build platform và ứng dụng.

### Checklist trước khi phát hành

- [ ] Đã xác định runtime owner và Jakarta EE profile/specification version.
- [ ] Đã chọn cùng thế hệ namespace `javax` hoặc `jakarta` cho mỗi boundary.
- [ ] Đã phân biệt API, implementation, provider và container capabilities.
- [ ] Đã chọn scope Maven/Gradle theo deployment model thực tế.
- [ ] Servlet API không bị đóng gói trùng container ngoài chủ đích.
- [ ] Các provider cần thiết có mặt tại runtime, không chỉ compile classpath.
- [ ] JPA/Validation/CDI/JAX-RS provider được tích hợp phù hợp với transaction/container.
- [ ] Không coi umbrella API/BOM là implementation runtime.
- [ ] Đã kiểm tra các dependency bắc cầu có API/provider sai thế hệ.
- [ ] Đã kiểm tra Gradle WAR provided configurations hoặc Maven provided behavior.
- [ ] Với reusable library, đã xem public signatures và published dependency metadata.
- [ ] Đã kiểm tra `WEB-INF/lib`, fat/thin JAR hoặc EAR library layout.
- [ ] Đã kiểm tra `META-INF/services` và provider discovery trong artifact cuối.
- [ ] Đã xác minh JDK/class-file level của dependency và runtime.
- [ ] Đã chạy integration tests trên đúng server/container/embedded runtime đích.
- [ ] Đã kiểm tra classloader conflicts, duplicate JARs và provider versions.
- [ ] Có strategy cho rolling deployment/rollback nếu đổi API generation.
- [ ] Có dependency graph, compatibility matrix và release evidence để truy nguyên.

**Kết luận:** Chuyển Java EE sang Jakarta EE và nâng JDK không chỉ là thay tọa độ Maven/Gradle. API dependency giải quyết việc biên dịch; implementation/provider và runtime container giải quyết khả năng chạy; scope đóng gói quyết định những gì được đưa vào artifact và những gì phải do môi trường cung cấp. Khi chọn scope theo đúng mô hình triển khai, đồng bộ namespace/version và kiểm tra **artifact cuối trên runtime thật**, nhóm mới có thể chứng minh migration tương thích thay vì chỉ đạt một bản build thành công.
