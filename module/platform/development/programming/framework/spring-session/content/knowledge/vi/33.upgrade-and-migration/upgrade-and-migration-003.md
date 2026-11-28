# Servlet `javax`, `jakarta` và yêu cầu tương thích container

Khi nâng cấp Spring Session qua thế hệ Spring Framework và Spring Boot, thay đổi quan trọng là chuyển từ Servlet API dùng package `javax.servlet.*` sang `jakarta.servlet.*`. Đây là thay đổi namespace ở cấp bytecode và kiểu Java, không phải đổi tên đơn thuần trong cấu hình. Một filter được biên dịch với `javax.servlet.Filter` không thể thay thế filter cần `jakarta.servlet.Filter`, dù hai interface có tên và vai trò gần giống nhau.

Spring Session nằm trực tiếp trên Servlet API trong ứng dụng web truyền thống. `SessionRepositoryFilter`, request/response wrapper, cookie resolver và các integration khác phải được biên dịch cho đúng namespace mà container cung cấp. Vì vậy, cần nâng cấp đồng bộ Spring Boot, Spring Framework, Spring Session, Spring Security, Servlet API, test libraries và Servlet container. Chỉ đổi dependency Spring Session hoặc thay import trong một vài class thường không đủ.

## 1. Vì sao `javax.servlet` và `jakarta.servlet` không tương thích nhị phân?

Trước Jakarta EE 9, Servlet API dùng package `javax.servlet`. Từ Jakarta EE 9, các API Jakarta EE chuyển sang package `jakarta.*`, bao gồm Servlet. Hai kiểu sau là hai kiểu Java khác nhau:

```java
// Hệ sinh thái Servlet cũ
import javax.servlet.Filter;
import javax.servlet.FilterChain;
import javax.servlet.ServletRequest;
import javax.servlet.ServletResponse;
```

```java
// Hệ sinh thái Jakarta Servlet
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
```

Một class khai báo `implements javax.servlet.Filter` không triển khai `jakarta.servlet.Filter`. JVM phân biệt hai kiểu dựa trên tên nhị phân đầy đủ, bao gồm package. Do đó, class cũ không thể được đăng ký như một Jakarta filter chỉ vì tên interface giống nhau.

Các lỗi thường gặp khi trộn namespace:

- `ClassNotFoundException` hoặc `NoClassDefFoundError` với `javax/servlet/...` hay `jakarta/servlet/...`.
- `ClassCastException` khi classloader nhìn thấy hai API hoặc hai kiểu không tương thích.
- Lỗi khởi tạo filter/listener vì container không nhận interface mà class triển khai.
- Lỗi compile do method signature dùng kiểu request/response sai namespace.
- Lỗi deploy khi WAR mang Servlet API không tương thích với container.

Không có cơ chế tự động khiến một `javax.servlet.Filter` trở thành `jakarta.servlet.Filter` tại runtime. Đây là ranh giới tương thích phải giải quyết ở dependency và artifact.

## 2. Mốc chuyển đổi của Spring ecosystem

Việc chuyển namespace gắn với các thế hệ framework:

| Thành phần | Thế hệ `javax.servlet` | Thế hệ `jakarta.servlet` |
|---|---|---|
| Spring Framework | 5.x | 6.x trở lên |
| Spring Boot | 2.x | 3.x trở lên |
| Spring Session | 2.x | 3.x trở lên |
| Spring Security | 5.x | 6.x trở lên |
| Servlet API | `javax.servlet.*` | `jakarta.servlet.*` |

Bảng này mô tả ranh giới namespace chính, không thay thế bảng tương thích chính thức của từng bản phát hành. Cần kiểm tra Java baseline, phiên bản Spring Boot BOM, Spring Session, Spring Security và container cho đúng release cụ thể. Spring Boot 3 yêu cầu Java 17 trở lên; các phiên bản Spring Framework/Spring Session mới cũng có yêu cầu runtime riêng.

Một ứng dụng Spring Boot 2/Spring Framework 5 thường thuộc hệ sinh thái Servlet `javax`. Một ứng dụng Spring Boot 3/Spring Framework 6 thuộc hệ sinh thái Jakarta Servlet. Không chọn Spring Session version độc lập với Spring Boot BOM; dùng dependency management được hỗ trợ để tránh kéo nhầm module.

## 3. Tương thích với Servlet container

Container phải triển khai cùng thế hệ Servlet API mà ứng dụng được biên dịch để sử dụng. Ví dụ các dòng container phổ biến:

| Container line | Servlet namespace/API | Ghi chú |
|---|---|---|
| Tomcat 9 | `javax.servlet`, Servlet 4.0 | Phù hợp ứng dụng trên nền Java EE 8/Servlet 4 |
| Tomcat 10.0 | `jakarta.servlet`, Servlet 5.0 | Bắt đầu dòng Jakarta EE 9 |
| Tomcat 10.1 | `jakarta.servlet`, Servlet 6.0 | Dòng Jakarta EE 10 |
| Jetty 10 | `javax.servlet`, Servlet 4.0 | Thế hệ trước Jakarta namespace |
| Jetty 11 | `jakarta.servlet`, Servlet 5.0 | Jakarta EE 9 era |
| Jetty 12 | Có các environment EE riêng | Chọn đúng environment EE8/EE9/EE10/EE11 theo ứng dụng và bản Jetty |
| Undertow 2.2 line | Chủ yếu `javax.servlet` / EE8 | Kiểm tra bản phân phối và dependency cụ thể |
| Undertow 2.3 line | Jakarta namespace | Kiểm tra mức Servlet/Jakarta EE được hỗ trợ bởi bản cụ thể |

Không chỉ dựa vào số phiên bản container. Kiểm tra Servlet specification mà container thực sự cung cấp và ma trận hỗ trợ của Spring Boot. Với embedded server, Spring Boot BOM thường quản lý phiên bản container phù hợp. Với external container, đội triển khai phải bảo đảm server cài đặt tương thích với WAR.

### Lưu ý về Tomcat migration tool

Tomcat cung cấp công cụ hỗ trợ chuyển ứng dụng cũ sang Jakarta namespace trong một số kịch bản migration. Công cụ chuyển đổi bytecode/configuration có thể hữu ích như bước chuyển tiếp, nhưng không thay thế việc nâng cấp source code, dependencies, test và quy trình build. Không coi một WAR được biến đổi tại deploy là giải pháp lâu dài nếu các thư viện bên trong vẫn thuộc hệ sinh thái cũ hoặc không được hỗ trợ.

## 4. Spring Session filter phải khớp Servlet API

Trong ứng dụng Servlet, Spring Session đăng ký `SessionRepositoryFilter` để bọc request/response và thay `HttpSession` container bằng session lưu trong Redis/JDBC hoặc repository khác.

Filter này phải triển khai đúng `Filter` interface của namespace tương ứng. Nếu ứng dụng Jakarta nhưng kéo Spring Session module được biên dịch với `javax.servlet`, filter không thể được container Jakarta đăng ký đúng cách.

Các thành phần liên quan cũng cần đồng nhất:

- `SessionRepositoryFilter` và các request/response wrapper.
- `HttpSessionIdResolver` hoặc `CookieSerializer`.
- Servlet filters, listeners và `ServletContainerInitializer` tùy chỉnh.
- Spring Security filter chain và `SecurityContextRepository`.
- MVC infrastructure, multipart support và error/async dispatch.
- Test utilities tạo mock request, response, session và filter chain.

Spring Boot thường tự cấu hình Spring Session khi dependency và store được phát hiện. Khi ứng dụng có filter registration tùy chỉnh hoặc WAR triển khai ngoài, cần kiểm tra filter thực sự được đăng ký và thứ tự của nó. Spring Session filter phải bọc request trước những thành phần cần truy cập `HttpSession`, thường đứng trước Spring Security filter chain.

## 5. Chọn đúng dependency và tránh trộn API

Với ứng dụng dùng Spring Boot, ưu tiên dependency starter và BOM phù hợp thay vì tự chỉ định từng phiên bản thư viện. Ví dụ Maven ở mức khái quát:

```xml
<!-- Ứng dụng thuộc hệ Spring Boot 3 / Jakarta Servlet -->
<dependency>
    <groupId>org.springframework.session</groupId>
    <artifactId>spring-session-data-redis</artifactId>
</dependency>
```

Hoặc dùng JDBC repository:

```xml
<dependency>
    <groupId>org.springframework.session</groupId>
    <artifactId>spring-session-jdbc</artifactId>
</dependency>
```

Ví dụ không khai báo version vì Spring Boot dependency management nên quản lý phiên bản tương thích. Với dự án không dùng Boot, cần chọn Spring Session/Spring Framework/Spring Security/Servlet API versions theo ma trận chính thức.

Không thêm đồng thời `javax.servlet-api` và `jakarta.servlet-api` vào cùng ứng dụng với kỳ vọng chúng có thể thay thế nhau. Không đóng gói Servlet API implementation trong WAR khi container phải cung cấp API đó. Với Maven, dependency API thường được khai báo `provided` nếu cần compile nhưng container cung cấp lúc runtime; cách cụ thể phụ thuộc kiểu packaging và build plugin.

## 6. Kiểm tra dependency tree

Khi gặp lỗi namespace, trước hết xác định artifact nào kéo Servlet API và Spring Session vào classpath.

Với Maven:

```bash
mvn dependency:tree
mvn dependency:tree -Dincludes=javax.servlet:javax.servlet-api
mvn dependency:tree -Dincludes=jakarta.servlet:jakarta.servlet-api
```

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency servlet-api --configuration runtimeClasspath
```

Kiểm tra:

- Có cả `javax.servlet-api` và `jakarta.servlet-api` ngoài dự kiến không?
- Spring Session module thuộc thế hệ nào?
- Spring Framework và Spring Security có cùng thế hệ namespace không?
- Container embedded/external đang cung cấp Servlet API nào?
- Một dependency cũ có mang theo filter/listener dựa trên `javax.servlet` không?
- Servlet API có bị đóng gói vào WAR hoặc fat JAR sai cách không?

Đừng chỉ xem dependency khai báo trực tiếp. Một thư viện logging, security adapter hoặc framework cũ có thể kéo API cũ bắc cầu vào runtime.

## 7. Không thay thế mọi `javax` bằng `jakarta`

Một lỗi migration phổ biến là tìm và thay toàn bộ chuỗi `javax.` trong source. Không phải mọi package bắt đầu bằng `javax` đều thuộc Jakarta EE.

Một số API thuộc Java SE vẫn giữ namespace `javax`, ví dụ:

- `javax.crypto.*`
- `javax.net.*`
- `javax.sql.*`
- `javax.naming.*`
- `javax.management.*`
- `javax.xml.*`

Chỉ chuyển những API đã được Jakarta EE chuyển namespace, chẳng hạn Servlet, Persistence, Validation, JAX-RS, CDI, JMS và các API Jakarta EE liên quan. Kiểm tra từng import và dependency. Không đổi `javax.sql.DataSource` thành `jakarta.sql.DataSource`; Java SE vẫn cung cấp `javax.sql.DataSource`.

### Ví dụ chuyển filter

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

Nhưng nếu class cũng dùng `javax.sql.DataSource`, import đó vẫn giữ nguyên. Cần sửa theo package/API thực sự đã chuyển, không dùng replace toàn cục thiếu phân biệt.

## 8. Filter, listener và cấu hình Servlet tùy chỉnh

Các class ứng dụng có thể trực tiếp phụ thuộc Servlet API:

- `Filter`, `FilterChain`, `FilterConfig`.
- `HttpServletRequest`, `HttpServletResponse`, `HttpSession`.
- `HttpSessionListener`, `HttpSessionAttributeListener`.
- `ServletContextListener` và `ServletContext`.
- `AsyncContext`, `AsyncListener` và dispatcher types.
- `ServletContainerInitializer` và registration APIs.

Tất cả các import, method signature, annotation và class được tham chiếu phải dùng cùng namespace. Ví dụ listener dùng `javax.servlet.http.HttpSessionListener` không thể được Jakarta container đăng ký như `jakarta.servlet.http.HttpSessionListener`.

Kiểm tra cả cấu hình khai báo:

- `web.xml` namespace/schema và version.
- `@WebFilter`, `@WebListener`, `@WebServlet`.
- `FilterRegistrationBean` và servlet initializer.
- `ServletContextInitializer` trong Spring Boot.
- Các thư viện web cũ đóng gói filter hoặc listener.

Nếu ứng dụng không dùng `web.xml`, không có nghĩa không còn Servlet API dependency; annotation và auto-configuration vẫn dựa vào API tương ứng.

## 9. Tương thích embedded container và external container

### Embedded container

Với executable JAR, Spring Boot thường đóng gói embedded Tomcat/Jetty/Undertow theo dependency đã quản lý. Khi nâng cấp Boot, nên nâng cấp cùng BOM và không override riêng container nếu không có lý do tương thích đã xác minh.

Kiểm tra startup log, dependency tree và integration test thực sự khởi động server. Một test chỉ tạo `ApplicationContext` có thể không phát hiện vấn đề đăng ký filter ở Servlet container.

### External container và WAR

Với WAR triển khai vào Tomcat/Jetty bên ngoài:

- Container phải hỗ trợ Servlet namespace/version mà WAR yêu cầu.
- Servlet API của container không được bị thay bằng một bản API khác trong `WEB-INF/lib`.
- Các dependency web cần được đóng gói đúng scope.
- `SpringBootServletInitializer` và servlet initializer phải tương thích với Boot version.
- Kiểm tra context path, filter mapping, listener và error/async dispatch sau deploy.

Một WAR chạy được trên Tomcat 9 không có nghĩa chạy được trên Tomcat 10.1 sau khi chỉ thay server. WAR cũ vẫn tham chiếu `javax.servlet` trong bytecode và cần được build/migrate cho Jakarta.

## 10. Spring Session và dữ liệu session tồn tại qua migration

Chuyển từ `javax.servlet` sang `jakarta.servlet` là thay đổi API ở tầng web. Dữ liệu session trong Redis/JDBC là một vấn đề tương thích riêng. Việc hai ứng dụng cùng đọc một cookie hoặc cùng trỏ đến Redis không bảo đảm chúng có thể đọc cùng serialized attributes.

Các điểm cần đánh giá:

- Spring Session 2.x và 3.x có cùng định dạng nội bộ/serializer đang cấu hình không?
- Principal hoặc `SecurityContext` có chứa class đổi package hoặc thay đổi phiên bản không?
- Session attribute có lưu class của ứng dụng hoặc Servlet API không?
- Các node cũ và mới có thể chạy đồng thời trong rolling deployment không?
- Session cũ có thể được giữ đến hết TTL hay cần invalidate/migrate?
- Cookie name, domain, path và resolver có giữ nguyên không?

### Không lưu Servlet object vào session

Không lưu `HttpServletRequest`, `HttpServletResponse`, `ServletContext`, `FilterConfig` hoặc object phụ thuộc container trong session. Các object này không phải dữ liệu người dùng bền vững và không nên serialize. Nếu session cũ từng chứa class ứng dụng phụ thuộc `javax.servlet`, việc chuyển namespace có thể khiến deserialize thất bại.

### Session ID cookie có thể giống nhưng payload vẫn không tương thích

Cookie là HTTP header nên tên cookie và chuỗi ID có thể được giữ nguyên qua nâng cấp. Tuy nhiên, ứng dụng mới chỉ tìm thấy session nếu repository namespace/schema và ID resolver tương thích; tiếp theo nó còn phải deserialize được attribute. Một session cũ có thể tồn tại trong Redis nhưng không đọc được bởi code mới.

Không coi việc cookie vẫn gửi được là bằng chứng migration session thành công. Cần test request sau deploy với cookie thật và session payload được tạo từ phiên bản cũ.

## 11. Chiến lược nâng cấp theo giai đoạn

Một migration an toàn thường cần tách nâng cấp API/container khỏi thay đổi session schema nếu có thể.

1. **Inventory:** xác định Boot, Framework, Security, Session, Java, Servlet API, container và dependencies trực tiếp.
2. **Build migration:** chuyển source imports thuộc Jakarta, cập nhật dependencies và plugin theo BOM.
3. **Compile/test:** sửa filter/listener/initializer và test utilities; không dùng global replace với mọi `javax`.
4. **Container validation:** khởi động bằng container Jakarta tương thích và kiểm tra filter registration.
5. **Session compatibility:** kiểm tra serializer, principal, SecurityContext và attributes được lưu bởi phiên bản cũ.
6. **Rollout plan:** quyết định rolling deployment, blue/green, drain hoặc maintenance window.
7. **Data strategy:** giữ reader tương thích, migrate session hoặc invalidate có kiểm soát.
8. **Production verification:** theo dõi deserialize errors, session not-found, login rate và repository failures.

Nếu phiên bản cũ và mới không thể cùng chạy trên một container hoặc không tương thích dữ liệu session, dùng blue/green hoặc maintenance window có thể phù hợp hơn rolling deployment. Đừng để node `javax` và node `jakarta` cùng nhận traffic mà chưa chứng minh được repository, cookie và payload tương thích.

## 12. Blue/green và rolling deployment

Với blue/green, hai cụm chạy độc lập trong giai đoạn chuyển đổi. Có thể:

- Cho cụm mới dùng Redis namespace/schema riêng, rồi yêu cầu login lại khi chuyển traffic.
- Dùng một store chung chỉ khi đã chứng minh format, classpath và semantics session tương thích.
- Drain request của cụm cũ, chờ session hết hạn hoặc chủ động invalidate theo chính sách.
- Giữ khả năng rollback traffic mà không buộc bản cũ đọc payload mới không tương thích.

Với rolling deployment, node cũ và mới chạy đồng thời. Điều này chỉ an toàn nếu cả hai namespace API không xung đột trong hạ tầng riêng và dữ liệu session được đọc/ghi tương thích. Vì `javax.servlet` và `jakarta.servlet` không thể dùng chung một Servlet container instance như cùng một API, cách triển khai có thể cần hai pool/container tách biệt trong giai đoạn chuyển đổi.

## 13. Kiểm thử container compatibility

Không chỉ kiểm tra compile. Cần chạy ứng dụng trên đúng container mục tiêu.

Một checklist kiểm thử:

1. Khởi động embedded/external container theo đúng phiên bản dự kiến.
2. Xác nhận application context khởi tạo và không có `NoClassDefFoundError` cho Servlet API.
3. Xác nhận `SessionRepositoryFilter` được đăng ký đúng một lần.
4. Xác nhận filter đứng trước Spring Security filter chain.
5. Tạo session và xác nhận cookie được phát theo cấu hình.
6. Gửi request tiếp theo và tải lại attribute từ Redis/JDBC.
7. Kiểm tra login, `SecurityContext`, logout và session ID rotation.
8. Kiểm tra redirect, error dispatch và async dispatch nếu ứng dụng sử dụng.
9. Kiểm tra listener/initializer tùy chỉnh.
10. Triển khai WAR thật nếu production dùng external container.

MockMvc hữu ích cho MVC và security flow nhưng không thay thế test khởi động Servlet container. Test cần dùng đúng filter registration và repository thật để phát hiện lỗi namespace/runtime.

## 14. Kiểm thử tương thích session qua nâng cấp

Tạo fixture session bằng build cũ rồi đọc bằng build mới:

- Session chứa string/number/collection chuẩn.
- Session chứa custom DTO principal.
- Session chứa `SecurityContext` và `GrantedAuthority`.
- Session có attribute được thêm/đổi tên/đổi kiểu.
- Session được ghi bằng serializer thực tế của production.
- Session cũ gần hết TTL và session mới vừa được tạo.

Xác nhận ứng dụng mới có thể đọc dữ liệu hoặc xử lý fallback đã định. Nếu không thể deserialize, cần ghi nhận và xử lý session cụ thể, không để request cấp quyền dựa trên dữ liệu không đọc được.

### Test rollback

Nếu build mới ghi payload mà build cũ không đọc được, rollback binary có thể khiến các session mới lỗi. Test rollback cần kiểm tra dữ liệu được ghi trong giai đoạn nâng cấp và khả năng reader cũ xử lý chúng. Nếu không thể, phương án rollback phải bao gồm invalidate/migrate session hoặc quay lại store namespace cũ, không chỉ đổi image ứng dụng.

## 15. Lỗi thường gặp khi trộn namespace

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `NoClassDefFoundError: javax/servlet/Filter` | Artifact cũ chạy trên Jakarta container | Nâng cấp dependency/build sang Jakarta hoặc dùng container javax tương thích |
| `NoClassDefFoundError: jakarta/servlet/...` | Artifact Jakarta chạy trên container javax | Chọn container Jakarta hoặc build đúng thế hệ cũ |
| Filter không được đăng ký | Filter triển khai interface sai namespace hoặc registration lỗi | Kiểm tra type signature, filter registration và thứ tự |
| `ClassCastException` giữa Servlet API types | Có API khác namespace hoặc duplicate classloader | Loại dependency API xung đột và kiểm tra classloader/container |
| Compile fail ở `HttpServletRequest` | Import `javax`/`jakarta` không đồng nhất | Sửa import theo API mục tiêu và kiểm tra thư viện liên quan |
| WAR chạy embedded nhưng fail external | Container cung cấp Servlet API khác hoặc WAR đóng gói sai | Test trên đúng external container và scope dependency |
| Session cũ không deserialize | Attribute/principal class hoặc serializer thay đổi | Compatibility fixture, converter, drain/invalidate |
| Request chạy nhưng không có shared session | Filter/repository không được cấu hình hoặc cookie/store khác | Kiểm tra filter, resolver, namespace và store |

## 16. Runbook chẩn đoán khi deploy thất bại

Khi ứng dụng không khởi động hoặc session không hoạt động sau migration:

1. Ghi nhận Boot/Framework/Session/Security/JDK/container versions của artifact và môi trường.
2. Lấy root cause đầu tiên trong startup/deploy log, không chỉ dòng wrapper exception.
3. Kiểm tra dependency tree và nội dung artifact để tìm `javax.servlet`/`jakarta.servlet` references.
4. Xác định Servlet API do container cung cấp và API bị đóng gói trong WAR/JAR.
5. Kiểm tra `SessionRepositoryFilter` và filter order.
6. Gửi request test, xác nhận cookie và repository load/save.
7. Nếu lỗi chỉ xảy ra với session cũ, kiểm tra serializer và classpath của attribute.
8. Nếu cần rollback, xác định build cũ có thể đọc dữ liệu mới đã ghi không.
9. Chọn invalidate/drain/migrate có kiểm soát nếu session format không tương thích.
10. Theo dõi lỗi classloading, deserialize, session-not-found và login lại sau phục hồi.

Không giải quyết lỗi bằng cách thêm cả hai Servlet API vào runtime. Điều đó thường che khuất nguyên nhân và có thể tạo classloading conflict khó đoán.

## 17. Checklist trước khi phát hành

- Chốt Java baseline và Spring Boot BOM.
- Chọn Spring Framework, Spring Session và Spring Security cùng thế hệ namespace.
- Xác nhận Servlet API của embedded/external container.
- Kiểm tra container version và Jakarta EE environment tương ứng.
- Loại bỏ dependency `javax.servlet` cũ khỏi Jakarta runtime.
- Không thay thế nhầm Java SE `javax.*` packages.
- Chuyển filter, listener, initializer và test imports thuộc Jakarta EE.
- Kiểm tra Servlet API dependency scope và WAR contents.
- Xác nhận `SessionRepositoryFilter` được đăng ký đúng một lần và đúng thứ tự.
- Test cookie, Redis/JDBC session round-trip, login, logout và async/error dispatch.
- Test fixture session cũ, principal và SecurityContext qua serializer thực tế.
- Có kế hoạch drain, invalidate, migrate và rollback session data.
- Theo dõi classloading, deserialization errors và tỷ lệ login lại sau rollout.

Chuyển từ `javax.servlet` sang `jakarta.servlet` là thay đổi tương thích nhị phân trên toàn bộ Servlet stack. Spring Session, Spring Security, filter tùy chỉnh, test libraries và container phải cùng namespace; một API cũ không thể được dùng thay cho API Jakarta chỉ bằng đổi cấu hình. Hãy nâng cấp theo BOM, kiểm tra dependency tree, triển khai trên đúng container và kiểm thử filter/session lifecycle thực tế. Đồng thời xem serialized session data là một hợp đồng riêng: cookie ID có thể vẫn giống nhưng principal hoặc attribute cũ vẫn có thể không deserialize được. Kế hoạch rollout phải xử lý cả API compatibility lẫn dữ liệu session đang tồn tại.
