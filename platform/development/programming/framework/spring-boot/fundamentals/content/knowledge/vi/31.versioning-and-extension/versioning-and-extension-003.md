# Nhận diện thay đổi javax sang jakarta khi gặp mã cũ

> **Spring Boot Fundamentals · Phiên bản và mở rộng**  
> Khi đọc một dự án Spring Boot cũ, bạn có thể gặp các import như `javax.servlet.*`, `javax.persistence.*` hoặc `javax.validation.*`. Trong dự án mới hơn, những API tương ứng thường nằm dưới namespace `jakarta.*`. Đây là hệ quả của quá trình chuyển Java EE sang Jakarta EE sau khi quyền phát triển nền tảng được chuyển sang Eclipse Foundation. **Thay đổi namespace là một thay đổi tương thích ở cấp API và bytecode**, không phải thao tác đổi tên package đơn giản. Muốn nhận diện và xử lý đúng mã cũ, cần biết API nào đã chuyển, API nào vẫn thuộc Java SE, phiên bản Spring Boot/container nào đang sử dụng và dependency nào còn phụ thuộc namespace cũ.

## 1. Vì sao có cả javax và jakarta?

Trong nhiều năm, các API enterprise của Java được phát triển dưới tên Java Platform, Enterprise Edition (Java EE). Các API quen thuộc gồm Servlet, JPA, Bean Validation, JAX-RS, JMS và nhiều công nghệ khác. Chúng sử dụng namespace `javax.*`.

Sau khi Java EE được chuyển giao cho Eclipse Foundation, nền tảng tiếp tục phát triển dưới tên **Jakarta EE**. Do ràng buộc về thương hiệu và quyền sử dụng namespace `javax`, Jakarta EE 9 thực hiện một thay đổi lớn: các API thuộc nền tảng Jakarta chuyển từ `javax.*` sang `jakarta.*`.

Ví dụ:

- `javax.servlet.Filter` trở thành `jakarta.servlet.Filter`.
- `javax.persistence.Entity` trở thành `jakarta.persistence.Entity`.
- `javax.validation.Valid` trở thành `jakarta.validation.Valid`.

Điều này không có nghĩa mọi package bắt đầu bằng `javax` đều bị đổi. Nhiều package `javax` là API của chính Java SE và vẫn tồn tại trong JDK.

### 1.1. Mốc chuyển đổi quan trọng

| Thế hệ | Nền tảng thường gặp | Namespace enterprise phổ biến |
| --- | --- | --- |
| Java EE 8 | Java EE 8 APIs | `javax.*` |
| Jakarta EE 8 | Jakarta EE 8, tương thích namespace Java EE 8 | `javax.*` |
| Jakarta EE 9 | Bước chuyển namespace | `jakarta.*` |
| Jakarta EE 10 | Các phiên bản API Jakarta EE mới hơn | `jakarta.*` |
| Spring Framework 5 / Spring Boot 2 | Thế hệ Spring trước migration chính | Chủ yếu tích hợp Java EE/`javax` APIs |
| Spring Framework 6 / Spring Boot 3 | Thế hệ Spring đã chuyển sang Jakarta | `jakarta` APIs cho các integration enterprise tương ứng |

Jakarta EE 8 vẫn dùng `javax` vì tương thích với Java EE 8. Sự thay đổi package bắt đầu ở Jakarta EE 9; không phải cứ thấy chữ “Jakarta” trong tên platform là chắc chắn import đã là `jakarta`.

### 1.2. Vì sao không thể giữ nguyên package để tương thích?

Namespace là một phần của tên lớp nhị phân. JVM không xem:

```text
javax.servlet.Filter
jakarta.servlet.Filter
```

là cùng một type. Hai class có tên nhị phân khác nhau, method signatures khác nhau và không thể thay thế trực tiếp cho nhau.

Một class được biên dịch để implement `javax.servlet.Filter` không tự động trở thành implementation của `jakarta.servlet.Filter` chỉ vì hai interface có cùng method names.

### 1.3. Đây là thay đổi nền tảng, không chỉ thay đổi Spring

Spring Framework 6 chuyển các integration tương ứng sang Jakarta APIs. Spring Boot 3 dựa trên Spring Framework 6 và yêu cầu Java 17 trở lên. Vì thế, nâng ứng dụng từ Boot 2 lên Boot 3 thường kéo theo việc nâng dependency, container, ORM, validation provider và các thư viện liên quan.

Không nên xem đây là một lần sửa import độc lập.

## 2. Nhận diện nhanh mã cũ trong dự án

Khi mở code hoặc đọc stack trace, hãy nhận diện package trước khi quyết định sửa.

### 2.1. Các import thường gặp trong ứng dụng Java EE cũ

```java
import javax.servlet.Filter;
import javax.servlet.http.HttpServletRequest;
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
import javax.annotation.PostConstruct;
import javax.inject.Inject;
```

Trong ứng dụng Spring Boot 3 / Spring Framework 6, các API Jakarta tương ứng thường có dạng:

```java
import jakarta.servlet.Filter;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.annotation.PostConstruct;
import jakarta.inject.Inject;
```

Một số annotation của Spring vẫn giữ package `org.springframework.*`, ví dụ `@Autowired`, `@Component`, `@Service` và `org.springframework.transaction.annotation.Transactional`. Không đổi mọi annotation chỉ vì dự án nâng lên Boot 3.

### 2.2. Dùng tìm kiếm source để lập danh sách

Trong repository, có thể tìm các import cũ bằng ripgrep:

```bash
rg -n "import javax\\.(servlet|persistence|validation|annotation|inject|transaction|ws\\.rs|jms|mail|xml\\.bind)" .
```

Lệnh trên là bước inventory ban đầu. Nó không tìm hết mọi trường hợp:

- Code có thể dùng fully qualified class name trong annotation hoặc string.
- XML descriptor có thể khai báo namespace/schema cũ.
- File `META-INF/services` có thể chứa tên interface cũ.
- Generated source có thể được tạo lại từ schema.
- Dependency JAR có thể tham chiếu `javax` dù source của ứng dụng không có import nào.

Có thể tìm rộng hơn:

```bash
rg -n "javax\\." src pom.xml build.gradle build.gradle.kts
```

Kết quả rộng cần được phân loại; **không thay thế hàng loạt tất cả kết quả**.

### 2.3. Xem dependency graph, không chỉ source

Một project có thể không import `javax.servlet` trực tiếp nhưng một thư viện cũ vẫn yêu cầu API đó ở runtime.

Maven:

```bash
./mvnw dependency:tree
```

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Khi cần tìm version cụ thể:

```bash
./gradlew dependencyInsight --dependency servlet-api --configuration runtimeClasspath
```

Tìm những dependency như:

- Servlet API.
- JPA API và ORM provider.
- Bean Validation API/provider.
- JAXB/JAX-WS.
- JAX-RS implementation.
- JMS client.
- Security, SAML, SOAP hoặc thư viện tích hợp container.

Một source file dùng `jakarta.persistence.Entity` nhưng runtime lại chứa Hibernate hoặc persistence API thế hệ cũ vẫn có thể thất bại.

## 3. Không phải mọi javax đều chuyển sang jakarta

Đây là quy tắc quan trọng nhất khi sửa mã cũ: **chỉ chuyển các API thuộc Java EE/Jakarta EE đã được đổi namespace**.

Nhiều API trong JDK vẫn giữ nguyên tên `javax`.

### 3.1. Những package Java SE vẫn dùng javax

| Package | Tình trạng |
| --- | --- |
| `javax.sql.DataSource` | Java SE/JDBC; vẫn là `javax.sql` |
| `javax.crypto.*` | Java SE cryptography; vẫn là `javax.crypto` |
| `javax.net.*` | Java SE networking; vẫn là `javax.net` |
| `javax.naming.*` | Java Naming and Directory Interface; vẫn là `javax.naming` |
| `javax.management.*` | Java Management Extensions; vẫn là `javax.management` |
| `javax.security.auth.*` | Java SE security APIs; vẫn là `javax.security.auth` |
| `javax.xml.parsers.*` | Java SE XML APIs; vẫn là `javax.xml.parsers` |
| `javax.xml.transform.*` | Java SE XML transformation; vẫn là `javax.xml.transform` |
| `javax.xml.validation.*` | Java SE XML validation; vẫn là `javax.xml.validation` |
| `javax.xml.stream.*` | Java SE StAX; vẫn là `javax.xml.stream` |
| `javax.annotation.processing.*` | Java compiler annotation processing API; vẫn là `javax.annotation.processing` |
| `javax.lang.model.*` | Java compiler language model; vẫn là `javax.lang.model` |
| `javax.transaction.xa.*` | XA APIs thuộc Java SE module; vẫn là `javax.transaction.xa` |

Ví dụ:

```java
import javax.sql.DataSource;
import javax.crypto.Cipher;
import javax.naming.InitialContext;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.annotation.processing.Processor;
```

Các import này không cần đổi sang `jakarta` khi nâng Spring Boot 3.

### 3.2. Những package enterprise đã chuyển namespace

| API cũ | API Jakarta mới |
| --- | --- |
| `javax.servlet.*` | `jakarta.servlet.*` |
| `javax.persistence.*` | `jakarta.persistence.*` |
| `javax.validation.*` | `jakarta.validation.*` |
| `javax.annotation.*` (Common Annotations) | `jakarta.annotation.*` |
| `javax.inject.*` | `jakarta.inject.*` |
| `javax.transaction.*` (JTA APIs) | `jakarta.transaction.*` |
| `javax.ws.rs.*` | `jakarta.ws.rs.*` |
| `javax.jms.*` | `jakarta.jms.*` |
| `javax.websocket.*` | `jakarta.websocket.*` |
| `javax.faces.*` | `jakarta.faces.*` |
| `javax.enterprise.*` | `jakarta.enterprise.*` |
| `javax.batch.*` | `jakarta.batch.*` |
| `javax.resource.*` | `jakarta.resource.*` |
| `javax.xml.bind.*` | `jakarta.xml.bind.*` |
| `javax.xml.soap.*` | `jakarta.xml.soap.*` |
| `javax.mail.*` | `jakarta.mail.*` |
| `javax.activation.*` | `jakarta.activation.*` |
| `javax.json.*` | `jakarta.json.*` |

Bảng này giúp nhận diện các họ API phổ biến. Khi nâng một thư viện cụ thể, vẫn phải đối chiếu version và artifact coordinates của thư viện đó.

### 3.3. Ngoại lệ dễ nhầm: javax.transaction và javax.transaction.xa

JTA API cũ có các type như `javax.transaction.UserTransaction` và `javax.transaction.TransactionManager`; trong Jakarta chúng chuyển sang `jakarta.transaction.*`.

Nhưng `javax.transaction.xa.XAResource` là API Java SE và vẫn giữ package `javax.transaction.xa`.

Ví dụ code có thể hợp lệ trong một ứng dụng Jakarta:

```java
import jakarta.transaction.UserTransaction;
import javax.transaction.xa.XAResource;
```

Không đổi đồng loạt prefix `javax.transaction` thành `jakarta.transaction` bằng một thao tác text thiếu phân biệt.

### 3.4. Ngoại lệ dễ nhầm: javax.annotation và javax.annotation.processing

`javax.annotation.PostConstruct` thuộc Common Annotations cũ và được thay bằng `jakarta.annotation.PostConstruct` trong hệ sinh thái Jakarta.

Nhưng `javax.annotation.processing.Processor` thuộc Java compiler API và vẫn giữ nguyên.

Ví dụ:

```java
import jakarta.annotation.PostConstruct;
import javax.annotation.processing.ProcessingEnvironment;
```

Hai import này có thể cùng xuất hiện trong một ứng dụng Boot 3 mà không có mâu thuẫn.

### 3.5. Ngoại lệ dễ nhầm: javax.xml

Không phải toàn bộ `javax.xml` chuyển sang Jakarta.

`javax.xml.parsers`, `javax.xml.transform` và nhiều API XML của Java SE vẫn giữ nguyên. Những API enterprise như JAXB và SAAJ chuyển namespace:

```java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.soap.SOAPMessage;
import javax.xml.parsers.DocumentBuilderFactory;
```

Ngoài ra, từ Java 11, một số Java EE modules như JAXB/JAX-WS không còn được đóng gói sẵn trong JDK như các bản Java cũ. Việc thiếu class có thể là do dependency không được khai báo, ngay cả khi bạn chưa migration namespace.

## 4. Bản đồ các API Spring Boot thường bị ảnh hưởng

Khi nâng Spring Boot 2.x lên 3.x, một số họ API xuất hiện thường xuyên nhất.

### 4.1. Servlet API

Trước:

```java
import javax.servlet.Filter;
import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.ServletRequest;
import javax.servlet.ServletResponse;
```

Sau:

```java
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
```

Ví dụ filter:

```java
@Component
public class RequestTraceFilter implements Filter {

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        chain.doFilter(request, response);
    }
}
```

Chỉ thay import là phần method signature có thể được cập nhật theo API mới nếu dependency phù hợp đã được đưa vào. Nhưng nếu một third-party library vẫn trả về `javax.servlet.Filter`, nó không thể đăng ký như `jakarta.servlet.Filter`.

### 4.2. JPA / Persistence

Trước:

```java
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.Table;
import javax.persistence.ManyToOne;
```

Sau:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.ManyToOne;
```

Ví dụ entity:

```java
@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    private Long id;

    // ...
}
```

Hibernate 6, được dùng trong dòng Spring Boot 3, dựa trên Jakarta Persistence. Một entity còn mang `javax.persistence.Entity` không phải annotation Jakarta Persistence mà Hibernate 6 đang tìm kiếm.

Điều này có thể dẫn tới hiện tượng entity không được nhận diện hoặc metadata mapping không được tạo như mong đợi.

### 4.3. Bean Validation

Trước:

```java
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
import javax.validation.constraints.NotNull;
```

Sau:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
```

Ví dụ:

```java
public record CreateCustomerRequest(
        @NotBlank String name,
        @NotNull @Email String email) {
}
```

Nếu API type và validation provider không cùng namespace/version, constraint có thể không được phát hiện như mong đợi hoặc ứng dụng thiếu provider phù hợp.

### 4.4. Common Annotations

Trước:

```java
import javax.annotation.PostConstruct;
import javax.annotation.PreDestroy;
import javax.annotation.Resource;
```

Sau:

```java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import jakarta.annotation.Resource;
```

Ví dụ:

```java
@Component
public class CacheWarmup {

    @PostConstruct
    void initialize() {
        // Chuẩn bị cache sau khi dependency được inject.
    }

    @PreDestroy
    void shutdown() {
        // Giải phóng resource.
    }
}
```

Trong Spring, `@PostConstruct`/`@PreDestroy` vẫn là annotation lifecycle được hỗ trợ qua API Jakarta tương ứng. Không nhầm chúng với các callback Spring như `InitializingBean` hoặc `DisposableBean`.

### 4.5. Dependency Injection annotation

Trước:

```java
import javax.inject.Inject;
import javax.inject.Named;
```

Sau:

```java
import jakarta.inject.Inject;
import jakarta.inject.Named;
```

Spring cũng có annotation riêng:

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
```

`@Autowired` không chuyển thành `@Inject` hoặc ngược lại chỉ vì migration. Đây là hai bộ annotation có nguồn gốc khác nhau; hãy chọn API mà codebase và framework version đang hỗ trợ.

### 4.6. JTA transaction annotation khác Spring transaction annotation

JTA:

```java
import jakarta.transaction.Transactional;
```

Spring:

```java
import org.springframework.transaction.annotation.Transactional;
```

Cả hai có cùng tên annotation đơn giản nhưng là hai type khác nhau với semantics và integration tương ứng. Spring transaction management có thể hỗ trợ nhiều transaction annotation theo cấu hình, nhưng không nên đổi import theo tên ngắn mà không xác định code muốn dùng transaction model nào.

## 5. Spring Boot 2 và Spring Boot 3 khác nhau ra sao?

Một dấu hiệu mạnh để nhận diện codebase là Spring Boot major version.

| Đặc điểm | Spring Boot 2.x | Spring Boot 3.x |
| --- | --- | --- |
| Spring Framework | 5.x | 6.x |
| Java baseline | Dòng 2.x hỗ trợ các Java baseline cũ hơn; tùy minor | Java 17 trở lên |
| Enterprise API namespace | Thường là `javax` | Jakarta `jakarta` |
| Servlet ecosystem | Thường Servlet 4 / Tomcat 9 | Jakarta Servlet 6 / Tomcat 10.1 ở các cấu hình mặc định phù hợp |
| Persistence provider | Dòng Hibernate 5 phổ biến | Hibernate 6 |
| Validation API | `javax.validation` | `jakarta.validation` |
| Migration effort | Legacy code có thể tiếp tục chạy trong stack phù hợp | Phải đồng bộ Jakarta APIs và libraries |

Bảng này mô tả thế hệ điển hình, không thay thế compatibility matrix của một minor release cụ thể. Boot 2.x có nhiều minor versions và có thể dùng các dependency được nâng riêng; Boot 3.x cũng có nhiều release với server/provider versions khác nhau.

### 5.1. Boot 2.7 thường là điểm xuất phát của migration

Nhiều dự án nâng từ Boot 2.5/2.6 lên Boot 3 sẽ đi qua Boot 2.7 trước để xử lý deprecation và chuẩn bị. Điều này không bắt buộc cho mọi repository, nhưng là một chiến lược thường hữu ích.

Ở giai đoạn Boot 2.7:

- Dọn các API Spring đã deprecated.
- Cập nhật dependency còn được hỗ trợ.
- Loại bỏ các cấu hình cũ không còn phù hợp.
- Kiểm tra test suite và build reproducibility.
- Chuẩn bị Java 17 và plugin/toolchain tương thích.

Sau đó mới thực hiện namespace migration và nâng dependency sang thế hệ Jakarta.

### 5.2. Spring Framework 6 yêu cầu Java 17+

Nếu source đã đổi import sang `jakarta` nhưng CI vẫn chạy Java 11, ứng dụng vẫn có thể thất bại trước khi Spring context được tạo. Đây là lỗi baseline runtime/compiler, không phải lỗi namespace.

Kiểm tra:

```bash
java -version
./mvnw -version
./gradlew -version
```

Cần xác định cả JDK chạy Maven/Gradle và Java toolchain dùng compile/test.

### 5.3. Embedded Tomcat cũng phải cùng thế hệ

Một ứng dụng Boot 3 sử dụng Jakarta Servlet không thể triển khai trực tiếp vào Tomcat 9 vốn cung cấp Servlet API `javax.servlet` như một ứng dụng Jakarta Servlet 6.

Các thế hệ Tomcat phổ biến:

| Tomcat | Servlet namespace/specification |
| --- | --- |
| Tomcat 9 | Java EE 8 / Servlet 4, `javax.servlet` |
| Tomcat 10.0 | Jakarta EE 9 / Servlet 5, `jakarta.servlet` |
| Tomcat 10.1 | Jakarta EE 10 / Servlet 6, `jakarta.servlet` |

Boot 3.x cần container phù hợp với Servlet generation mà release đó hỗ trợ. Đối với external WAR, phải kiểm tra server thực tế thay vì chỉ dựa vào embedded server version trong local build.

## 6. Vì sao javax và jakarta không tương thích nhị phân?

JVM dùng tên nhị phân của class/interface trong descriptor, constant pool và method signatures.

Giả sử một library được compile với:

```java
public class LegacyFilter implements javax.servlet.Filter {
}
```

Application mới mong đợi:

```java
jakarta.servlet.Filter filter = obtainFilter();
```

Không có phép chuyển đổi tự động giữa hai interface. Một class implement `javax.servlet.Filter` không implement `jakarta.servlet.Filter`.

### 6.1. Method signature cũng thay đổi

Một Servlet filter cũ:

```java
void doFilter(
        javax.servlet.ServletRequest request,
        javax.servlet.ServletResponse response,
        javax.servlet.FilterChain chain);
```

Một Servlet filter mới:

```java
void doFilter(
        jakarta.servlet.ServletRequest request,
        jakarta.servlet.ServletResponse response,
        jakarta.servlet.FilterChain chain);
```

Dù tên method và số lượng tham số giống nhau, descriptor khác vì các parameter types khác nhau.

### 6.2. Compile thành công không chứng minh runtime tương thích

Một dự án có thể compile vì có cả API JAR cũ và mới trên compile classpath. Nhưng runtime container chỉ cung cấp một namespace, dẫn tới lỗi linkage hoặc cast.

Không nên thêm cả `javax.servlet-api` và `jakarta.servlet-api` vào cùng một ứng dụng rồi hy vọng Spring tự chọn đúng bộ. Cần loại dependency cũ hoặc tách integration phù hợp.

### 6.3. Annotation cũ không được xem như annotation mới

Ví dụ:

```java
@javax.persistence.Entity
public class CustomerEntity {
}
```

không phải cùng annotation với:

```java
@jakarta.persistence.Entity
public class CustomerEntity {
}
```

Hibernate 6 không tự diễn giải annotation cũ như Jakarta Persistence annotation. Tên đơn giản `Entity` giống nhau không làm chúng trở thành cùng type.

### 6.4. Generic type, reflection và service loading cũng bị ảnh hưởng

Migration không chỉ ảnh hưởng import ở method bình thường:

- Reflection code gọi `getAnnotation` với type cũ sẽ không tìm thấy annotation mới.
- Generic signature và interface implementation có thể tham chiếu namespace cũ.
- SPI service descriptors có thể khai báo interface provider cũ.
- Proxy và generated bytecode có thể giữ method descriptors cũ.
- XML mapping có thể trỏ tới class hoặc schema cũ.

Vì thế, migration cần kiểm tra cả source, generated artifacts, resources và runtime dependencies.

## 7. Dependency coordinates: import mới cần API artifact mới

Một lỗi thường gặp là sửa source imports nhưng vẫn giữ dependency artifact thế hệ cũ.

### 7.1. Ví dụ Servlet API

Cũ:

```xml
<dependency>
    <groupId>javax.servlet</groupId>
    <artifactId>javax.servlet-api</artifactId>
    <scope>provided</scope>
</dependency>
```

Mới:

```xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <scope>provided</scope>
</dependency>
```

Trong Spring Boot Web application, thường để Boot starter/BOM quản lý server API thay vì khai báo thủ công một version servlet-api tùy ý. Ví dụ trên giúp nhận diện sự thay đổi coordinates.

### 7.2. Ví dụ Persistence API

Cũ:

```xml
<dependency>
    <groupId>javax.persistence</groupId>
    <artifactId>javax.persistence-api</artifactId>
</dependency>
```

Mới:

```xml
<dependency>
    <groupId>jakarta.persistence</groupId>
    <artifactId>jakarta.persistence-api</artifactId>
</dependency>
```

Nếu dùng Spring Boot Data JPA starter, dependency management thường chọn API/provider tương thích. Tránh khai báo API version riêng nếu không có lý do rõ ràng.

### 7.3. Ví dụ Bean Validation API

Cũ:

```xml
<dependency>
    <groupId>javax.validation</groupId>
    <artifactId>validation-api</artifactId>
</dependency>
```

Mới:

```xml
<dependency>
    <groupId>jakarta.validation</groupId>
    <artifactId>jakarta.validation-api</artifactId>
</dependency>
```

Chỉ có API không đồng nghĩa có provider. Trong ứng dụng Boot, starter validation thường đưa implementation phù hợp vào runtime.

### 7.4. Không phải mọi dependency group đều đổi tên theo cùng một quy tắc

Artifact của Hibernate, Hibernate Validator, Jackson, JAXB implementation và các thư viện khác có versioning/artifact naming riêng. Không thể áp dụng quy tắc “thay javax thành jakarta ở groupId” cho tất cả dependency.

Hãy dùng:

- Spring Boot dependency management/BOM.
- Release notes và migration guide của library.
- Dependency tree thực tế.
- Compatibility matrix của container/provider.

### 7.5. Tránh version drift

Một ví dụ rủi ro:

- Spring Boot 3.x.
- Hibernate 5.x bị pin thủ công.
- Persistence API Jakarta mới.
- Một extension Hibernate chỉ hỗ trợ Hibernate 5.
- Servlet API Jakarta mới nhưng filter library cũ vẫn implement javax.

Mỗi dependency riêng lẻ có thể tồn tại, nhưng tổng thể không tạo được một stack tương thích. Khi nâng major framework, ưu tiên đồng bộ bộ version do Boot quản lý rồi mới override khi có lý do.

## 8. XML descriptors và resource không được sửa bằng import refactor

Mã cũ có thể không còn import `javax` nhưng vẫn chứa cấu hình XML từ Java EE.

### 8.1. web.xml

Một descriptor cũ có thể bắt đầu:

```xml
<web-app
    xmlns="http://xmlns.jcp.org/xml/ns/javaee"
    version="4.0">
    ...
</web-app>
```

Jakarta Servlet thế hệ mới sử dụng Jakarta EE XML namespace/schema tương ứng, ví dụ descriptor Servlet 6 có namespace dạng:

```xml
<web-app
    xmlns="https://jakarta.ee/xml/ns/jakartaee"
    version="6.0">
    ...
</web-app>
```

Nếu ứng dụng dùng Servlet initializer của Spring Boot và không cần descriptor tùy chỉnh, có thể không cần `web.xml`. Nhưng nếu còn filter/listener/servlet declarations, security constraints hoặc metadata khác, hãy migration descriptor theo schema mà container target hỗ trợ.

### 8.2. persistence.xml

Descriptor persistence cũ có thể dùng namespace/schema của JPA 2.x. Jakarta Persistence 3.x sử dụng schema/namespace Jakarta tương ứng.

Nếu dự án dùng persistence unit khai báo thủ công, cập nhật:

- XML namespace và schema version.
- Provider class name.
- Persistence unit properties.
- Entity class references.
- Các mapping file liên quan.

Không sửa schema nếu ứng dụng không dùng `persistence.xml`; Spring Boot có thể cấu hình persistence từ properties và entity scanning.

### 8.3. beans.xml và validation mapping

Các descriptor CDI hoặc validation mapping cũng có thể tham chiếu schema namespace và class names cũ. Kiểm tra đúng specification version, không đổi toàn bộ URL XML theo một mẫu chung.

### 8.4. `META-INF/services`

Java SPI lưu provider class names trong resource:

```text
META-INF/services/javax.servlet.ServletContainerInitializer
```

Nếu SPI interface đã chuyển namespace, resource tương ứng cũng phải dùng tên interface mới:

```text
META-INF/services/jakarta.servlet.ServletContainerInitializer
```

Đây là một ví dụ điển hình cho thấy migration chỉ sửa import Java là chưa đủ.

## 9. Third-party libraries: nơi migration thường khó nhất

Một ứng dụng có thể sửa hết code của mình nhưng vẫn phụ thuộc vào thư viện cũ.

Ví dụ:

- Một filter library chỉ implement `javax.servlet.Filter`.
- Một plugin tích hợp JPA dùng `javax.persistence.EntityManager`.
- Một validation extension tham chiếu `javax.validation.ConstraintValidator`.
- Một SOAP/JAXB library cũ dùng `javax.xml.bind`.
- Một security adapter phụ thuộc Servlet API thế hệ cũ.

### 9.1. Phân loại dependency

| Loại thư viện | Câu hỏi cần kiểm tra |
| --- | --- |
| Framework integration | Có release hỗ trợ Spring Framework 6/Boot 3 không? |
| Servlet filter/security | Implement `jakarta.servlet` hay `javax.servlet`? |
| ORM extension | Hỗ trợ Hibernate 6/Jakarta Persistence không? |
| Validation custom constraint | Implement Jakarta Validation API chưa? |
| Serialization/XML | Có dùng Jakarta JAXB/SAAJ không? |
| Generated SDK | Code generator đã tạo namespace mới chưa? |
| Internal company library | Có source để nâng cấp và publish lại không? |
| Container plugin | Hỗ trợ external Tomcat/Jakarta Servlet version nào? |

### 9.2. Ưu tiên bản phát hành Jakarta-native

Nếu vendor đã có version mới tương thích Jakarta, ưu tiên nâng lên bản đó. Một bản thư viện có tên gần giống nhưng version khác major có thể đã thay namespace và behavior.

Đọc release notes, POM metadata và source JAR khi cần. Không suy luận chỉ từ tên artifact.

### 9.3. Nếu không có thư viện thay thế

Các lựa chọn có thể gồm:

1. Tìm implementation khác có hỗ trợ Jakarta.
2. Nâng hoặc fork thư viện nội bộ để build với Jakarta APIs.
3. Thay integration bằng một adapter nhỏ của ứng dụng.
4. Dùng bytecode transformation trong giai đoạn chuyển tiếp nếu được hỗ trợ và kiểm thử.
5. Tách legacy application khỏi runtime Jakarta mới trong một service/process riêng, giao tiếp qua HTTP/message contract.

Không cố ép một class `javax` vào interface `jakarta` bằng cast hoặc reflection. Chúng là hai API khác nhau.

## 10. Nhận diện lỗi khi trộn javax và jakarta

### 10.1. Compile error: package không tồn tại

Ví dụ:

```text
package javax.persistence does not exist
```

Có thể dependency Jakarta mới đã được đưa vào nhưng source vẫn dùng import cũ. Hoặc dependency API cũ đã bị loại khỏi classpath.

Hướng xử lý:

- Xác định target framework version.
- Nếu dự án dùng Boot 3, đổi import thuộc Persistence sang `jakarta.persistence`.
- Kiểm tra starter/provider dependency.
- Build lại module có source lỗi.

### 10.2. NoClassDefFoundError: javax/servlet/...

Ví dụ:

```text
java.lang.NoClassDefFoundError: javax/servlet/Filter
```

Một thư viện hoặc class runtime vẫn cần Servlet API cũ. Nếu ứng dụng đang chạy Boot 3/Tomcat 10.1, đây thường là dấu hiệu dependency cũ chưa migration.

Dùng dependency tree để tìm artifact chứa tham chiếu `javax.servlet` và nâng cấp/thay thế.

### 10.3. ClassCastException giữa javax và jakarta

Ví dụ:

```text
SomeFilter cannot be cast to jakarta.servlet.Filter
```

Nếu `SomeFilter` chỉ implement `javax.servlet.Filter`, nó không thể được đăng ký như `jakarta.servlet.Filter`. Kiểm tra thư viện filter, container integration và các API JAR trùng lẫn.

### 10.4. NoSuchMethodError hoặc AbstractMethodError

Một library được compile với một API generation nhưng runtime nạp API generation khác. Method descriptors không còn khớp, hoặc interface mới có contract khác.

Kiểm tra:

- Version API thực tế.
- Version implementation.
- Classpath order/shading.
- Dependency mediation.
- Artifact cũ được copy vào thư mục server shared libraries.

### 10.5. JPA không nhận entity

Một entity có `javax.persistence.Entity` trong ứng dụng dùng Hibernate 6/Jakarta Persistence có thể không được nhận như entity Jakarta.

Triệu chứng có thể là không tìm thấy entity, lỗi mapping hoặc không có metadata tương ứng. Kiểm tra import annotation và provider/API version trước khi thay đổi component scanning.

### 10.6. Bean Validation không chạy

Một constraint annotation thuộc `javax.validation` có thể không được provider Jakarta Validation nhìn thấy như constraint Jakarta. Hãy kiểm tra import của constraint, provider version và dependency graph.

### 10.7. `@PostConstruct` không được gọi như kỳ vọng

Nếu source dùng `javax.annotation.PostConstruct` nhưng runtime Spring 6 chỉ có Jakarta Common Annotations integration tương ứng, lifecycle annotation cũ có thể không được nhận diện. Đổi sang `jakarta.annotation.PostConstruct` và bảo đảm API có trên classpath khi cần.

### 10.8. Lỗi container khi deploy WAR

Một WAR được compile với `jakarta.servlet` không thể chạy như một Servlet 4 application trên Tomcat 9. Ngược lại, WAR cũ dùng `javax.servlet` không tự trở thành Jakarta Servlet app trên Tomcat 10 chỉ nhờ đổi server version.

Phải nâng ứng dụng và container theo cùng generation hoặc dùng một migration/transformation strategy có kiểm soát.

## 11. Chiến lược migration từ Spring Boot 2 sang Spring Boot 3

Không nên bắt đầu bằng find-and-replace toàn repository. Một quy trình theo giai đoạn sẽ giúp phân biệt lỗi namespace với lỗi do nâng framework/provider.

### Bước 1 — Chụp trạng thái hiện tại

Ghi lại:

- Spring Boot và Spring Framework version.
- Java compile/runtime version.
- Maven/Gradle và plugin versions.
- Servlet container version.
- Hibernate/JPA/Validation provider.
- Các thư viện security, SOAP, messaging, batch.
- Build/test status trước migration.
- Những WAR/JAR artifact đang deploy.

Có baseline giúp biết lỗi mới xuất hiện ở bước nào.

### Bước 2 — Chọn target compatibility

Xác định target Spring Boot 3 release, Java 17+, servlet container và các library versions tương thích.

Không nâng Boot trước khi xác nhận những dependency trọng yếu có bản Jakarta-compatible.

### Bước 3 — Nâng Java toolchain

Ví dụ Maven:

```xml
<properties>
    <java.version>17</java.version>
</properties>
```

Gradle:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Cấu hình CI, developer JDK và runtime image nhất quán. Kiểm tra annotation processors, compiler plugins và test runner hỗ trợ JDK target.

### Bước 4 — Nâng framework và dependency management

Nâng Spring Boot parent/plugin/BOM theo release đã chọn. Tránh giữ Spring Framework 5 hoặc Hibernate 5 bằng cách pin thủ công nếu target Boot 3 yêu cầu generation mới.

Chạy dependency tree để xác nhận không còn API/provider cũ bị kéo vào.

### Bước 5 — Chuyển import theo API cụ thể

Sửa những họ namespace đã chuyển: Servlet, Persistence, Validation, Common Annotations, JAX-RS, JMS, JAXB...

Giữ nguyên Java SE packages như `javax.sql`, `javax.crypto`, `javax.naming` và `javax.xml.parsers`.

### Bước 6 — Sửa descriptors và SPI resources

Kiểm tra web.xml, persistence.xml, beans.xml, validation mappings, `META-INF/services` và XML schemas.

Nếu file được generate, sửa source schema/generator template thay vì chỉ sửa generated output.

### Bước 7 — Nâng third-party libraries

Đối chiếu các library integrations với Jakarta support. Đặc biệt chú ý security filters, servlet extensions, ORM types, validation constraints và SOAP clients.

### Bước 8 — Build theo module

Build module lõi trước, sau đó adapter và application. Lỗi compile đầu tiên giúp xác định source/import/API chưa đồng bộ. Không bỏ qua module ít được sử dụng vì nó có thể chỉ lỗi khi đóng gói toàn project.

### Bước 9 — Chạy test theo tầng

- Unit tests cho logic thuần.
- Persistence tests cho JPA/provider.
- MVC/Servlet tests cho filter/controller.
- Context startup tests.
- Integration tests với database/message broker.
- Smoke test artifact đã đóng gói.
- External container deployment test nếu build WAR.

### Bước 10 — Chạy thử trong runtime target

Không chỉ chạy từ IDE. Dùng chính JAR/WAR artifact và Java/container runtime sẽ deploy. Xác nhận logging, port, security, migration, shutdown và health check.

### Bước 11 — Loại dependency cũ và xác nhận lại

Dùng dependency analysis và scan source/resources để tìm reference còn sót. Phân biệt reference hợp lệ của Java SE với enterprise API cũ. Cuối cùng build sạch từ môi trường CI.

## 12. Dùng công cụ tự động: khi nào hữu ích, khi nào nguy hiểm?

### 12.1. Find-and-replace

Thay toàn bộ `javax.` thành `jakarta.` là cách nguy hiểm vì có thể phá các package Java SE còn nguyên.

Ví dụ không được đổi:

```java
import javax.sql.DataSource;
import javax.crypto.Cipher;
import javax.naming.InitialContext;
import javax.xml.parsers.DocumentBuilderFactory;
```

Một phép thay thế mù có thể biến các import hợp lệ thành package không tồn tại.

Nếu dùng IDE replace, chỉ áp dụng theo danh sách package đã xác nhận, kiểm tra diff và compile ngay sau mỗi nhóm.

### 12.2. OpenRewrite

OpenRewrite có recipes phục vụ nâng Spring Boot và chuyển namespace Java EE sang Jakarta trong những trường hợp được hỗ trợ.

Một recipe có thể cập nhật:

- Java imports.
- Một số dependency coordinates.
- Một số cấu hình.
- Một số API usages theo rule đã định nghĩa.

Nhưng tool không thể tự biết mọi custom library nội bộ đã có bản Jakarta-compatible chưa, cũng không thể tự quyết định business behavior cần thay đổi ra sao.

Luôn:

1. Chọn recipe/version phù hợp.
2. Chạy trên branch migration.
3. Review diff.
4. Kiểm tra những file XML/resources/generated sources.
5. Build/test toàn bộ module.
6. Đối chiếu dependency graph và runtime behavior.

### 12.3. Eclipse Transformer và Tomcat Migration Tool

Có các công cụ transform artifact/bytecode từ Java EE namespace sang Jakarta, ví dụ Eclipse Transformer hoặc Apache Tomcat Jakarta EE Migration Tool.

Chúng có thể hữu ích khi xử lý một số legacy application hoặc dependency không có source migration ngay lập tức. Tuy nhiên:

- Không phải mọi library đều có thể transform an toàn.
- Reflection strings, serialization metadata, XML, service descriptors và bytecode có thể cần xử lý tương ứng.
- Runtime behavior vẫn phải tương thích với Jakarta APIs target.
- Một artifact được transform không đồng nghĩa vendor hỗ trợ nó.
- Công cụ không thay thế việc nâng framework/container/provider.

Xem transformation là một phần của migration plan có kiểm thử, không phải bảo đảm tương thích tự động.

### 12.4. Generated code

Nếu source sinh ra từ WSDL, XSD, OpenAPI hoặc annotation processor, import có thể quay lại namespace cũ sau lần generate tiếp theo.

Cần kiểm tra:

- Generator version.
- Plugin configuration.
- Templates.
- Annotation processor dependencies.
- Generated source directories.
- CI code generation task.

Sửa generated output mà không sửa generator thường chỉ tạo ra một bản sửa tạm thời.

## 13. Tương thích Servlet container khi nâng WAR

Với WAR truyền thống, namespace migration phải khớp với external container.

### 13.1. Tomcat 9 và Tomcat 10+

Tomcat 9 cung cấp Servlet API thế hệ `javax.servlet`. Tomcat 10 chuyển sang `jakarta.servlet`. Tomcat 10.1 hỗ trợ Jakarta Servlet 6.0.

Một WAR Boot 3/Spring 6 dùng Jakarta Servlet cần container tương thích. Deploy vào Tomcat 9 không phải một phép thử hợp lệ cho ứng dụng Jakarta Servlet.

### 13.2. Không copy Servlet API JAR cũ vào WAR để chữa lỗi

Nếu container cung cấp Servlet API, dependency scope phải phản ánh runtime ownership. Thêm `javax.servlet-api` vào `WEB-INF/lib` của một WAR Jakarta không giúp adapter cũ tương thích; nó chỉ đưa thêm một bộ type không tương thích vào classpath.

### 13.3. Tomcat migration tool có thể hỗ trợ chuyển WAR cũ

Tomcat cung cấp công cụ migration để transform một số ứng dụng Java EE 8 thành Jakarta EE phù hợp với Tomcat 10. Đây là phương tiện chuyển tiếp hữu ích cho legacy deployments, nhưng vẫn cần test:

- Servlet filters/listeners.
- JSP/tag libraries nếu có.
- XML descriptors.
- Third-party libraries.
- Security integration.
- JPA/validation APIs ngoài phạm vi Servlet.
- Application-specific reflection/serialization.

Không giả định transform Servlet namespace đồng nghĩa toàn bộ stack enterprise đã được migration hoàn tất.

## 14. Spring-specific APIs nào không cần đổi?

Khi nâng Spring Boot 3, nhiều class thuộc Spring vẫn giữ package và tên.

Ví dụ:

```java
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.annotation.Transactional;
```

Các annotation này vẫn thuộc Spring Framework. Không đổi thành package `jakarta` vì không có API Jakarta tương ứng cùng vai trò.

Một số API Spring có thể đã đổi behavior hoặc deprecated giữa major versions, nhưng đó là vấn đề migration riêng, không phải namespace conversion.

### 14.1. `@Transactional` là ví dụ dễ nhầm

Spring:

```java
import org.springframework.transaction.annotation.Transactional;
```

JTA cũ:

```java
import javax.transaction.Transactional;
```

JTA mới:

```java
import jakarta.transaction.Transactional;
```

Nếu source dùng Spring annotation, import vẫn là `org.springframework.transaction.annotation.Transactional` trong Boot 3. Đừng đổi thành `jakarta.transaction.Transactional` chỉ vì nhìn thấy từ khóa transaction.

### 14.2. `@Autowired` không chuyển thành `@Inject`

Spring:

```java
import org.springframework.beans.factory.annotation.Autowired;
```

Jakarta Inject:

```java
import jakarta.inject.Inject;
```

Cả hai có thể biểu đạt dependency injection trong môi trường phù hợp, nhưng không phải cùng type. Migration không yêu cầu thay toàn bộ `@Autowired` bằng `@Inject`.

### 14.3. `@Component` không chuyển thành `@Named`

Spring:

```java
import org.springframework.stereotype.Component;
```

Jakarta Inject:

```java
import jakarta.inject.Named;
```

Đây là những annotation thuộc hệ sinh thái khác nhau. Chọn theo framework contract, không thay tên theo kiểu đồng nghĩa.

## 15. Các API đã rời JDK và vấn đề dependency riêng biệt

Một số package `javax` enterprise từng có trong JDK cũ nhưng đã bị loại khỏi JDK từ Java 11 theo lộ trình module removal. JAXB và JAX-WS là ví dụ nổi bật.

Điều này tạo ra hai loại lỗi khác nhau:

1. Source vẫn dùng API cũ nhưng dependency không còn tự có trong JDK.
2. Ứng dụng đã migration sang Jakarta nhưng chưa khai báo API/implementation tương ứng.

### 15.1. JAXB

Code cũ:

```java
import javax.xml.bind.JAXBContext;
```

Code Jakarta:

```java
import jakarta.xml.bind.JAXBContext;
```

Ngoài namespace, cần có API và implementation JAXB phù hợp trong dependency graph. Chỉ import package mới mà không có dependency runtime vẫn không đủ.

### 15.2. JAX-WS

Các API JAX-WS cũ có package `javax.xml.ws`; Jakarta version dùng `jakarta.xml.ws`. Tooling như wsimport, generated client và runtime implementation phải tương thích với target namespace.

Nếu WSDL client code được generate từ tool cũ, source có thể tiếp tục chứa `javax.xml.ws` sau khi project đã nâng Boot 3.

### 15.3. Phân biệt lỗi Java 11 với lỗi Jakarta migration

Một ứng dụng chạy Java 8 có thể dùng JAXB classes từ JDK. Khi chuyển lên Java 17, nó có thể gặp `ClassNotFoundException` dù vẫn đang dùng namespace cũ.

Đó là một thay đổi về JDK packaging. Migration sang Jakarta lại là thay đổi namespace/API generation. Hai vấn đề có thể cùng xuất hiện nhưng phải chẩn đoán riêng.

## 16. Lỗi thường gặp khi nâng cấp và cách điều tra

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| `package javax.persistence does not exist` | Source cũ nhưng dependency mới hoặc thiếu API cũ | Đổi sang Jakarta nếu target Boot 3; kiểm tra JPA starter |
| `NoClassDefFoundError: javax/servlet/Filter` | Library cũ cần Servlet javax | Tìm dependency và nâng bản Jakarta |
| `NoClassDefFoundError: jakarta/servlet/Servlet` | Runtime/container chưa cung cấp Jakarta Servlet | Kiểm tra Tomcat/Jetty và deployment mode |
| `ClassCastException` khi đăng ký Filter | Filter implement javax nhưng container đòi jakarta | Nâng filter library hoặc thay adapter |
| Hibernate không nhận Entity | Entity annotation thuộc javax Persistence | Đổi import và dùng Hibernate/JPA Jakarta |
| Validation không chạy | Constraint/provider không cùng namespace | Kiểm tra Jakarta Validation API/provider |
| `NoSuchMethodError` | API/provider/library version không tương thích | Dependency tree, BOM, runtime classpath |
| WAR chạy Boot 2 nhưng lỗi trên Tomcat 10 | WAR còn javax Servlet | Migration source/dependency hoặc transform có kiểm soát |
| Boot 3 WAR lỗi trên Tomcat 9 | Container chỉ hỗ trợ javax Servlet | Nâng external container |
| `javax.annotation.PostConstruct` không chạy | Lifecycle annotation cũ | Dùng `jakarta.annotation.PostConstruct` |
| XML deployment descriptor bị từ chối | Namespace/schema version cũ | Cập nhật descriptor theo container target |
| SPI provider không được tìm thấy | `META-INF/services` còn tên interface cũ | Sửa service descriptor và provider |
| JAXB class missing trên Java 17 | JAXB không còn bundled trong JDK | Thêm Jakarta JAXB API/implementation tương thích |
| Generated source lại có javax | Generator/plugin cũ | Nâng generator và template |
| Chỉ fail ở CI | CI JDK/container/dependency khác local | So sánh toolchain, runtime image, resolved graph |
| Source sạch nhưng runtime vẫn lỗi | Third-party bytecode chứa javax references | Scan dependency JAR/upgrade library |
| Cả javax và jakarta API cùng xuất hiện | Dependency tree trộn generation | Xác định dependency kéo API cũ, loại/upgrade |

### 16.1. Đọc full exception chain

Ví dụ:

```text
Caused by: java.lang.NoClassDefFoundError:
    javax/servlet/ServletRequest

    at com.vendor.legacy.LegacyFilter.initialize(...)
    ...

Caused by: java.lang.ClassNotFoundException:
    javax.servlet.ServletRequest
```

Frame `com.vendor.legacy.LegacyFilter` cho thấy thư viện vendor là nơi còn tham chiếu API cũ. Sửa import trong controller của ứng dụng sẽ không giải quyết được.

### 16.2. Tìm dependency sở hữu class cũ

Maven:

```bash
./mvnw dependency:tree -Dverbose
```

Gradle:

```bash
./gradlew dependencyInsight --dependency javax.servlet --configuration runtimeClasspath
```

Tên module có thể không trùng chính xác với package. Nếu dependencyInsight không tìm được do API được shade/relocate trong một JAR, cần kiểm tra nội dung archive hoặc scan bytecode.

### 16.3. So sánh local và CI

Kiểm tra:

- JDK thực tế.
- Spring Boot plugin/BOM version.
- Dependency lockfiles.
- Container base image.
- WAR/JAR artifact được deploy.
- Shared libraries của external Tomcat.
- Environment variables và build profiles.

Một local IDE có thể vô tình đưa API cũ từ module khác vào classpath, trong khi packaged artifact không có; hoặc ngược lại.

## 17. Quy trình kiểm tra source, resources và bytecode

Một migration đáng tin cậy nên có nhiều lớp kiểm tra.

### 17.1. Scan source imports

```bash
rg -n "import javax\\.(servlet|persistence|validation|annotation|inject|ws\\.rs|jms|mail|xml\\.bind)" src
```

Đây là bộ lọc để tìm các nhóm API thường phải migration. Mỗi kết quả cần xác nhận target package đã chuyển hay thuộc Java SE.

### 17.2. Scan resources

Tìm trong:

- `src/main/resources`.
- `src/test/resources`.
- `META-INF/services`.
- XML descriptors.
- WSDL/XSD/generated files.
- Templates có fully qualified class names.

Ví dụ:

```bash
rg -n "javax\\.(servlet|persistence|validation|xml\\.bind)" src/main/resources src/test/resources
```

### 17.3. Kiểm tra archive đã build

Với JAR:

```bash
jar tf target/application.jar
```

Với WAR:

```bash
jar tf target/application.war
```

Kiểm tra dependency JAR và resource descriptors được đóng gói. Một source import đã đổi không bảo đảm artifact deploy cũng được build lại từ source mới.

### 17.4. Scan bytecode khi cần

Các class compiled có thể chứa symbolic references tới namespace cũ. Công cụ như jdeps, javap hoặc bytecode analysis tool có thể giúp phát hiện dependency reference.

Ví dụ xem class:

```bash
javap -classpath path/to/library.jar -verbose com.vendor.LegacyFilter
```

Tìm constant pool entries hoặc method descriptors có `javax/servlet`. Cần chọn đúng classpath và tên class của JAR; với nested JAR trong executable Boot archive, có thể cần giải nén artifact trước.

### 17.5. Dependency graph là bằng chứng, không phải toàn bộ bằng chứng

Dependency tree cho thấy artifact coordinates và versions, nhưng không phải lúc nào cũng chỉ ra package nào được shade vào JAR hoặc class nào được generate. Kết hợp source search, resource search, dependency analysis và runtime stack trace.

## 18. Tương thích giữa modules trong một hệ thống lớn

Trong hệ thống nhiều module hoặc nhiều service, migration có thể diễn ra theo nhiều nhịp.

### 18.1. Không dùng chung một Servlet interface giữa hai generation

Một module legacy implement `javax.servlet.Filter` không thể được đăng ký trực tiếp vào Spring Boot 3 application đang yêu cầu `jakarta.servlet.Filter`.

Nếu cần giữ module cũ, tách nó khỏi Jakarta application boundary bằng process/API/message hoặc viết adapter mới dựa trên contract trung lập.

### 18.2. Chia service boundary thay vì trộn API

Ví dụ:

```text
Legacy service (Boot 2 / javax)
        |
        | HTTP/JSON or message contract
        v
New service (Boot 3 / jakarta)
```

HTTP/JSON contract không mang class identity Java của Servlet/JPA. Hai service có thể dùng namespace khác nhau miễn là schema/protocol chung được version và kiểm thử.

### 18.3. Shared library nên tránh phụ thuộc Servlet nếu không cần

Nếu một library chỉ chứa domain types hoặc DTO dùng chung, không nên kéo Servlet API vào dependency của nó. Điều đó làm library khó tái sử dụng giữa web stack cũ và mới.

Giữ shared contracts thuần Java hoặc dùng schema-based messages có thể giảm coupling. Nếu thật sự cần Servlet integration, tách module adapter riêng cho từng API generation khi migration song song là yêu cầu bắt buộc.

### 18.4. Không để javax và jakarta cùng định nghĩa cùng contract trong một module

Hai interface cùng tên nhưng khác package tạo ra hai type identities. Nếu cần tương thích tạm thời, phải viết adapter tường minh ở boundary và tránh rò rỉ type cũ vào core.

Không tạo một API chung bằng cách cast hoặc raw reflection để bỏ qua khác biệt type.

## 19. Một ví dụ migration Servlet Filter hoàn chỉnh

### 19.1. Code legacy

```java
package com.example.legacy;

import javax.servlet.Filter;
import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.ServletRequest;
import javax.servlet.ServletResponse;

import java.io.IOException;

public class LegacyTraceFilter implements Filter {

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        chain.doFilter(request, response);
    }
}
```

### 19.2. Code Jakarta

```java
package com.example.web;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;

import java.io.IOException;

public class TraceFilter implements Filter {

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        chain.doFilter(request, response);
    }
}
```

### 19.3. Đăng ký trong Spring

```java
@Configuration(proxyBeanMethods = false)
public class WebConfiguration {

    @Bean
    FilterRegistrationBean<TraceFilter> traceFilter() {
        FilterRegistrationBean<TraceFilter> registration =
                new FilterRegistrationBean<>();

        registration.setFilter(new TraceFilter());
        registration.addUrlPatterns("/*");
        registration.setOrder(10);

        return registration;
    }
}
```

`FilterRegistrationBean` là Spring Boot servlet integration API. Ở một ứng dụng Boot 3, filter generic type và import phải tương thích Jakarta Servlet.

Nếu một vendor library chỉ cung cấp `LegacyTraceFilter` implement javax, không thể truyền object đó vào registration bean Jakarta. Cần nâng thư viện hoặc viết filter adapter mới với API Jakarta.

### 19.4. Kiểm thử filter

Dùng MockMvc với full application context để xác nhận filter được đăng ký và áp dụng. Nếu filter phụ thuộc container behavior cụ thể, bổ sung HTTP test bằng RANDOM_PORT hoặc test trên external container phù hợp.

## 20. Một ví dụ migration JPA và Validation

### 20.1. Entity cũ

```java
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.Column;

@Entity
public class CustomerEntity {

    @Id
    private Long id;

    @Column(nullable = false)
    private String name;
}
```

### 20.2. Entity Jakarta

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Column;

@Entity
public class CustomerEntity {

    @Id
    private Long id;

    @Column(nullable = false)
    private String name;
}
```

Khi dùng Hibernate 6, đảm bảo entity và provider cùng dùng Jakarta Persistence. Các cấu hình Hibernate có thể có thêm breaking changes ngoài namespace, nên cần đọc migration guide của Hibernate version đang nâng.

### 20.3. Request validation cũ

```java
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;

public record CustomerRequest(
        @NotBlank String name) {
}
```

### 20.4. Request validation Jakarta

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

public record CustomerRequest(
        @NotBlank String name) {
}
```

Annotation `@Valid` trên controller parameter vẫn có vai trò cascade validation, nhưng import phải là Jakarta Validation type khi dùng stack Boot 3.

Nếu custom validator implement `ConstraintValidator`, cũng phải chuyển interface và các annotation liên quan sang `jakarta.validation.*`.

## 21. Kiểm thử migration sau khi thay namespace

Không nên kết thúc migration ngay khi source compile. Cần kiểm tra runtime integration.

### 21.1. Build sạch

Maven:

```bash
./mvnw clean verify
```

Gradle:

```bash
./gradlew clean test
```

Build sạch giúp loại output cũ từ trước migration. Nếu multi-module, xác nhận tất cả module được build theo cùng target generation.

### 21.2. Context startup test

```java
@SpringBootTest
class ApplicationMigrationTest {

    @Test
    void contextLoads() {
    }
}
```

Test này có thể phát hiện thiếu bean, API incompatibility, invalid configuration và provider initialization errors.

### 21.3. Servlet integration test

Dùng MockMvc hoặc RANDOM_PORT để kiểm tra:

- Filter registration.
- Request/response handling.
- Exception handlers.
- Security chain.
- JSON conversion.
- Servlet API integration.

Nếu target là external WAR, test deploy trên container đúng generation; embedded test không thay thế external deployment test.

### 21.4. Persistence test

Kiểm tra:

- Entity scanning.
- Hibernate startup.
- Schema validation/migration.
- Repository save/load.
- JPQL/native queries.
- Custom type converters.
- Transaction behavior.

Đừng chỉ kiểm tra application context khi entity mapping có thể chưa được chạm tới trong test.

### 21.5. Validation test

Kiểm tra constraint annotations được provider nhận diện và lỗi trả về đúng như mong muốn. Một endpoint trả 200 với dữ liệu sai có thể cho thấy validation annotation cũ không được provider mới phát hiện.

### 21.6. Smoke test packaged artifact

Chạy đúng JAR/WAR đã build, không chỉ chạy IDE. Với WAR, deploy lên external container target nếu đó là deployment model production.

## 22. Checklist chẩn đoán khi gặp mã javax cũ

Khi thấy một import hoặc stack trace `javax`, đi theo trình tự:

1. **Xác định package đầy đủ.** Không chỉ nhìn prefix `javax`.
2. **Xác định API thuộc Java SE hay Java EE/Jakarta EE.**
3. **Xác định Spring Boot/Spring Framework version.**
4. **Xác định target container/provider version.**
5. **Kiểm tra dependency coordinates và resolved versions.**
6. **Kiểm tra source, resources, XML và service descriptors.**
7. **Kiểm tra third-party libraries có reference namespace cũ không.**
8. **Build sạch để phát hiện compile/linkage errors.**
9. **Chạy context, persistence, web và validation tests phù hợp.**
10. **Deploy đúng artifact trên runtime target.**
11. **Chỉ dùng transformer khi đã xác định phạm vi và có test chứng minh.**
12. **Giữ nguyên những Java SE `javax` packages không thuộc migration.**

### 22.1. Câu hỏi quyết định

| Câu hỏi | Nếu câu trả lời là... | Hành động |
| --- | --- | --- |
| Package thuộc Java SE? | Có | Giữ `javax` |
| Package thuộc API Jakarta đã chuyển? | Có | Dùng `jakarta` cho target Jakarta stack |
| Dự án đang dùng Boot 2/Spring 5? | Có | Xác nhận Java EE/Jakarta EE 8 compatibility trước khi đổi |
| Dự án đang dùng Boot 3/Spring 6? | Có | Nâng API/provider/library sang Jakarta-compatible |
| Third-party library chỉ có javax release? | Có | Nâng/thay/fork/transform có kiểm soát hoặc cô lập service |
| Chạy WAR trên Tomcat 9? | Có | Đây là Servlet javax generation; không phù hợp trực tiếp với Boot 3 Jakarta Servlet |
| Source đã sạch nhưng runtime lỗi? | Có | Kiểm tra bytecode, dependencies, generated code và container shared libs |
| Lỗi chỉ xuất hiện trên Java 17? | Có | Phân biệt JDK module removals với namespace migration |

## 23. Bài thực hành: nhận diện và migration một module legacy

### Mục tiêu

Bắt đầu với một module Spring Boot 2.x giả định có Servlet filter, JPA entity, Bean Validation DTO và một dependency bên ngoài. Nâng nó lên target Spring Boot 3.x/Jakarta-compatible mà vẫn giữ business behavior.

### Bước 1 — Inventory

Tìm và ghi nhận:

- Boot/Spring version.
- Java toolchain.
- Servlet/JPA/Validation API dependencies.
- Tomcat/Jetty.
- Hibernate/Validation provider.
- Các import `javax`.
- XML descriptors.
- Service descriptors.
- Generated code.
- Third-party libraries.

Không sửa source ở bước này.

### Bước 2 — Phân loại import

Tạo ba nhóm:

1. Enterprise APIs cần chuyển sang Jakarta.
2. Java SE `javax` packages cần giữ nguyên.
3. Third-party package cần nâng version theo vendor.

Ví dụ:

| Import | Quyết định |
| --- | --- |
| `javax.servlet.Filter` | Chuyển `jakarta.servlet.Filter` |
| `javax.persistence.Entity` | Chuyển `jakarta.persistence.Entity` |
| `javax.validation.Valid` | Chuyển `jakarta.validation.Valid` |
| `javax.annotation.PostConstruct` | Chuyển `jakarta.annotation.PostConstruct` |
| `javax.sql.DataSource` | Giữ nguyên |
| `javax.crypto.Cipher` | Giữ nguyên |
| `javax.xml.parsers.DocumentBuilderFactory` | Giữ nguyên |
| `javax.annotation.processing.Processor` | Giữ nguyên |
| `javax.transaction.xa.XAResource` | Giữ nguyên |

### Bước 3 — Nâng target runtime

Chọn Java 17+ và Spring Boot 3 release phù hợp. Chọn container/provider version có hỗ trợ Jakarta APIs tương ứng.

### Bước 4 — Nâng dependencies

Dùng Boot BOM và các release Jakarta-compatible. Loại API/provider cũ bị kéo vào bởi transitive dependencies. Ghi lại lý do cho từng dependency override.

### Bước 5 — Migration source

Chuyển imports enterprise theo nhóm API. Compile sau mỗi nhóm lớn để dễ định vị lỗi. Không replace toàn bộ `javax.`.

### Bước 6 — Migration resources

Cập nhật descriptor/schema/SPI và code generator. Regenerate source nếu có WSDL/XSD/annotation processing.

### Bước 7 — Nâng third-party integration

Nâng servlet filter, security adapter, ORM extension, custom validator và SOAP/JMS library. Nếu không có Jakarta release, đánh giá khả năng thay thế hoặc isolate.

### Bước 8 — Build và scan

Chạy clean build, dependency tree, source/resource search. Kiểm tra không còn dependency enterprise javax ngoài những phần legacy được chủ động cô lập.

### Bước 9 — Test

Chạy unit, context startup, MVC, JPA, validation và integration tests. So sánh behavior trước/sau migration cho các use cases quan trọng.

### Bước 10 — Deploy smoke test

Chạy executable JAR hoặc deploy WAR lên đúng container target. Đọc startup log, kiểm tra endpoints, persistence, security và shutdown.

### Bước 11 — Ghi lại migration decisions

Tạo tài liệu nội bộ nêu:

- Namespace nào đã chuyển.
- Java SE packages nào vẫn là javax.
- Third-party library versions được nâng.
- Container minimum version.
- Những legacy integrations còn tồn tại.
- Những test xác nhận compatibility.

### Câu hỏi tự kiểm tra

1. Vì sao Java EE chuyển sang Jakarta EE?
2. Jakarta EE 8 có sử dụng namespace `javax` hay `jakarta`?
3. Thay đổi namespace chính thức bắt đầu ở Jakarta EE version nào?
4. Vì sao `javax.servlet.Filter` và `jakarta.servlet.Filter` không thể thay thế trực tiếp?
5. Những API nào của Java SE vẫn giữ prefix `javax`?
6. Vì sao `javax.annotation.PostConstruct` chuyển nhưng `javax.annotation.processing.Processor` vẫn giữ?
7. Vì sao `javax.transaction.xa.XAResource` là một ngoại lệ?
8. Spring Boot 3 yêu cầu Java baseline nào?
9. Vì sao Hibernate 6 cần Jakarta Persistence annotations?
10. Tomcat 9 khác Tomcat 10.1 ở Servlet namespace/specification thế nào?
11. Tại sao source đã đổi import nhưng runtime vẫn có thể lỗi?
12. `@Transactional` của Spring khác `jakarta.transaction.Transactional` ở đâu?
13. Vì sao phải kiểm tra `META-INF/services` khi migration?
14. Tại sao generated source có thể đưa javax imports trở lại?
15. Khi nào dùng OpenRewrite hoặc Eclipse Transformer?
16. Vì sao không nên replace toàn bộ chuỗi `javax.`?
17. Làm sao tìm một library còn tham chiếu `javax.servlet`?
18. Vì sao chỉ compile thành công chưa chứng minh WAR deploy được?
19. Khi nào nên cô lập legacy service thay vì trộn hai namespace?
20. Những integration tests nào cần chạy sau migration?

## 24. Bảng ghi nhớ nhanh

| Nội dung | Ghi nhớ |
| --- | --- |
| Java EE | Hệ sinh thái enterprise API thế hệ trước |
| Jakarta EE 8 | Vẫn dùng namespace `javax` |
| Jakarta EE 9 | Chuyển các API enterprise sang `jakarta` |
| Spring Boot 2 / Framework 5 | Thế hệ thường dùng `javax` integrations |
| Spring Boot 3 / Framework 6 | Jakarta APIs, Java 17+ |
| Servlet | `javax.servlet` → `jakarta.servlet` |
| JPA | `javax.persistence` → `jakarta.persistence` |
| Bean Validation | `javax.validation` → `jakarta.validation` |
| Common Annotations | `javax.annotation` → `jakarta.annotation` |
| Inject | `javax.inject` → `jakarta.inject` |
| JTA | `javax.transaction` → `jakarta.transaction` |
| XA | `javax.transaction.xa` vẫn là Java SE |
| JDBC | `javax.sql` vẫn là Java SE |
| Crypto | `javax.crypto` vẫn là Java SE |
| XML parser | `javax.xml.parsers` vẫn là Java SE |
| JAXB | `javax.xml.bind` → `jakarta.xml.bind` |
| JAX-RS | `javax.ws.rs` → `jakarta.ws.rs` |
| Spring annotation | `org.springframework.*` không tự đổi thành Jakarta |
| Dependency graph | Phải đồng bộ API, provider và implementation |
| Third-party libraries | Cần release Jakarta-compatible |
| XML/SPI resources | Có thể cần migration ngoài Java source |
| Tomcat 9 | Servlet `javax` generation |
| Tomcat 10.1 | Jakarta Servlet 6 generation |
| Migration tools | Hỗ trợ transform nhưng không thay thế compatibility testing |
| Full validation | Clean build + context + web + persistence + runtime smoke tests |

**Điểm cốt lõi:** Khi gặp mã cũ, đừng áp dụng quy tắc “thấy `javax` thì đổi thành `jakarta`”. Hãy xác định **package đó thuộc Java SE hay Jakarta EE**, rồi đối chiếu **Spring Boot/Spring Framework, API, provider, third-party library và container version**. Migration thành công khi toàn bộ source, dependency graph, descriptors, generated code và runtime cùng dùng một thế hệ API tương thích; các Java SE packages `javax` hợp lệ vẫn được giữ nguyên.
