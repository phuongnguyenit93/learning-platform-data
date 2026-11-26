# Lỗi dependency javax/Jakarta hoặc thư viện không tương thích

Một ứng dụng Spring Web Flow có thể biên dịch thành công nhưng thất bại khi khởi động, khi mở màn hình đầu tiên hoặc khi gửi form. Nếu stack trace chứa `javax.servlet`, `jakarta.servlet`, `NoSuchMethodError` hay `LinkageError`, nguyên nhân có thể nằm ở tập thư viện và môi trường chạy, trước cả khi engine xử lý state và transition.

Bài học thuộc chương **Chẩn đoán lỗi** của module **SPRING_WEB_FLOW**. Mục tiêu là xác định đúng loại xung đột, lần theo dependency và chọn một tập phiên bản nhất quán để hành trình nhiều bước, binding, validation, scope, tích hợp Spring MVC và kiểm thử hoạt động trên cùng nền tảng.

## 1. Hiểu đúng ranh giới javax và jakarta

Nhiều API Java EE đã chuyển package từ `javax.*` sang `jakarta.*` ở thế hệ Jakarta EE 9. Với tầng web, hai tên sau là hai kiểu Java khác nhau:

```java
javax.servlet.http.HttpServletRequest
jakarta.servlet.http.HttpServletRequest
```

Tên lớp ngắn giống nhau không tạo ra quan hệ tương thích kiểu. Một filter hoặc adapter được biên dịch cho `javax.servlet` không tự trở thành thành phần dùng `jakarta.servlet` chỉ vì runtime có thêm cả hai JAR API.

Tomcat mô tả thay đổi namespace này như một thay đổi không tương thích nhị phân, yêu cầu ứng dụng biên dịch lại theo API mới khi chuyển thế hệ tương ứng. Tham khảo [hướng dẫn chuyển từ Tomcat 9 sang Tomcat 10](https://tomcat.apache.org/migration-10.html).

### Không thay toàn bộ javax bằng jakarta

Một số package `javax` vẫn thuộc Java SE, ví dụ:

```java
import javax.sql.DataSource;
import javax.crypto.Cipher;
import javax.naming.InitialContext;
import javax.xml.parsers.DocumentBuilderFactory;
```

Chúng không phải bằng chứng ứng dụng còn dùng Servlet kiểu cũ. Thao tác thay chuỗi `javax.` thành `jakarta.` trên toàn bộ mã nguồn có thể làm hỏng cả những import vốn đúng.

Cần phân loại từng API: Servlet, Persistence, Validation, Faces, EL và các thành phần Java EE khác có đường nâng cấp riêng; thư viện Java SE hoặc thư viện độc lập cần được đánh giá theo chính API của nó.

Cũng không nên suy namespace chỉ từ group ID có chữ `jakarta`. Trong giai đoạn chuyển tiếp, một số bản API dưới tọa độ Jakarta vẫn thuộc namespace `javax`. Hãy xem phiên bản và package thực tế trong artifact.

## 2. Chọn một thế hệ nền tảng nhất quán

Các dòng Spring Web Flow gắn với những nền tảng khác nhau:

| Dòng Spring Web Flow | Nền Spring tương ứng | Namespace web | Ý nghĩa khi chẩn đoán |
| --- | --- | --- | --- |
| 2.5.x | Dòng Spring Framework 5 | `javax.servlet` | Không ghép trực tiếp tầng web này với một container chỉ cung cấp Jakarta Servlet |
| 3.0.x | Dòng Spring Framework 6 | `jakarta.servlet` | Nâng cả thư viện tích hợp và code ứng dụng sang thế hệ Jakarta phù hợp |
| 4.0.x | Baseline Spring Framework 7.0 | `jakarta.servlet`, Servlet 6.1 | Cùng namespace Jakarta vẫn phải đáp ứng đúng mức API và container |

Đây là bản đồ thế hệ để khoanh vùng, không phải cam kết rằng mọi bản vá bất kỳ trong cùng hàng đều đã được kiểm chứng với nhau. Cần chọn bộ phiên bản cụ thể theo tài liệu và dependency của bản phát hành đang dùng.

Tài liệu [Spring Web Flow 2.5](https://docs.spring.io/spring-webflow/docs/2.5.0.RELEASE/reference/html/whatsnew.html) mô tả đường nâng cấp lên Spring Framework 5. [Thông báo phát hành Spring Web Flow 3.0.0](https://spring.io/blog/2023/07/13/spring-web-flow-3-0-0-released/) xác định mục tiêu tương thích Spring Framework 6 và Jakarta EE. [Baseline của Spring Web Flow 4.0](https://docs.spring.io/spring-webflow/docs/current/reference/index.html) nêu Java 17 trở lên, Spring Framework 7.0 và Servlet 6.1.

Spring Framework 6 cũng yêu cầu Java 17 trở lên và nền Jakarta EE 9 trở lên; việc đổi dependency mà giữ JVM chạy thực tế quá cũ vẫn không đủ. Xem [Spring Framework 6.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.0-Release-Notes).

### Container có cùng namespace chưa chắc đủ mới

| Dòng Tomcat | Servlet API | Namespace |
| --- | --- | --- |
| 9.0.x | 4.0 | `javax.servlet` |
| 10.1.x | 6.0 | `jakarta.servlet` |
| 11.0.x | 6.1 | `jakarta.servlet` |

Bảng đặc tả này được công bố tại [Apache Tomcat: Which Version?](https://tomcat.apache.org/whichversion.html). Ví dụ, một stack đòi Servlet 6.1 không được coi là đáp ứng chỉ vì container cung cấp `jakarta.servlet` ở mức 6.0.

Khi ứng dụng dùng Spring Boot, cần xét cả dòng Boot quản lý Spring và embedded container. Web Flow vẫn phải được chọn tương thích với nền đó; không giả định đổi riêng phiên bản Web Flow sẽ nâng đồng bộ mọi thành phần.

## 3. Phân loại thông báo lỗi trước khi sửa dependency

| Biểu hiện | Hướng điều tra đầu tiên |
| --- | --- |
| `package javax.servlet... does not exist` khi compile | Code hoặc thư viện sinh mã còn dùng API cũ, trong khi compile classpath theo Jakarta |
| `package jakarta.servlet... does not exist` khi compile | Thiếu API compile hoặc ứng dụng đang dùng nền javax |
| `ClassNotFoundException` | Thành phần đang cố nạp một tên lớp không có trong classloader tương ứng |
| `NoClassDefFoundError: javax/servlet/...` | Bytecode đang tham chiếu API javax nhưng runtime không cung cấp đúng kiểu đó |
| `NoClassDefFoundError: jakarta/servlet/...` | Kiểm tra API runtime, container, scope dependency và JAR của thư viện gọi |
| `NoSuchMethodError` | Lớp đã được tìm thấy nhưng bản được nạp không có phương thức mà bytecode mong đợi |
| `AbstractMethodError` | Implementation không đáp ứng hợp đồng API mà runtime đang dùng |
| `ClassCastException` hoặc loader constraint violation | Kiểm tra cả namespace và classloader/JAR bị nạp trùng |
| `UnsupportedClassVersionError` | JVM chạy không đọc được phiên bản bytecode của lớp |

`NoSuchMethodError` là lỗi liên kết nhị phân, không phải lỗi nhập sai tên phương thức trong biểu thức flow theo nghĩa thông thường. Định nghĩa của JVM được mô tả tại [Java SE API: NoSuchMethodError](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/NoSuchMethodError.html).

Tuy nhiên, không quy mọi `NoClassDefFoundError` thành “thiếu JAR”. Nếu thông báo là `Could not initialize class`, cần tìm lỗi khởi tạo lớp xuất hiện trước đó, thường liên quan `ExceptionInInitializerError` và nguyên nhân gốc.

### Đọc stack trace theo chuỗi nguyên nhân

Giả sử log rút gọn có dạng:

```text
BeanCreationException: không khởi tạo được bean tích hợp web
  caused by: NoClassDefFoundError: javax/servlet/http/HttpServletRequest
```

Tên bean ở ngoài cùng giúp xác định nơi lỗi lộ ra; tên lớp thiếu ở nguyên nhân bên trong cho biết hợp đồng nhị phân đang bị yêu cầu. Nếu môi trường là Jakarta, câu hỏi tiếp theo là: **JAR nào vẫn được biên dịch với `javax.servlet`?**

Đừng sửa `flow.xml` chỉ vì bean lỗi có liên quan Web Flow. Khi class nền còn chưa nạp được, đổi `view-state`, event hay transition thường không tác động tới nguyên nhân.

## 4. Thu thập bằng chứng ở bốn lớp

Trước khi thay phiên bản, ghi lại bốn tập thông tin:

1. **Runtime:** JVM thực sự chạy tiến trình, phiên bản container và kiểu triển khai JAR/WAR.
2. **Dependency đã resolve:** phiên bản được Maven/Gradle chọn, kể cả phụ thuộc bắc cầu và override.
3. **Artifact đã đóng gói:** JAR nào thật sự nằm trong gói triển khai.
4. **Class được nạp:** classloader và vị trí nguồn của lớp bị nghi ngờ.

Bốn lớp này có thể khác nhau. IDE dùng JDK 21 không chứng minh service trên máy chủ cũng chạy JDK 21. Dependency tree sạch không chứng minh thư mục thư viện dùng chung của application server không chứa Spring cũ.

Một bản ghi chẩn đoán hữu ích:

```text
Triệu chứng: mở flow thất bại trước khi render view
Nguyên nhân sâu: thiếu javax.servlet.http.HttpServletRequest
JVM runtime: phiên bản lấy từ tiến trình đang chạy
Container: tên và phiên bản thực tế
Spring Web Flow: bản đã resolve và JAR thực tế
Spring Framework: spring-core, spring-context, spring-webmvc...
Thư viện nghi ngờ: artifact và đường dependency kéo nó vào
```

Không chỉ ghi “đã cập nhật lên Jakarta”. Thông tin cần đủ cụ thể để người khác đối chiếu lại.

## 5. Lần theo dependency bằng Maven hoặc Gradle

Các lệnh dưới là ví dụ dùng trong dự án ứng dụng cần chẩn đoán trên PowerShell. Chọn nhóm lệnh tương ứng với build tool của dự án; không cần chạy cả hai.

### Maven

```powershell
.\mvnw.cmd dependency:tree

.\mvnw.cmd dependency:tree "-Dincludes=org.springframework:*,org.springframework.webflow:*,javax.servlet:*,jakarta.servlet:*" -Dverbose

.\mvnw.cmd help:effective-pom
```

Bản đầy đủ của cây dependency giúp thấy đường kéo vào; bản lọc giúp tập trung vào Spring và Servlet. Effective POM hỗ trợ xác định dependency management hoặc profile đang ảnh hưởng đến phiên bản.

Maven Dependency Plugin cung cấp goal `dependency:tree` và các tùy chọn lọc; tham khảo [tài liệu dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html).

Đừng bỏ qua các thư viện liên quan khi lỗi xuất hiện ở view hoặc validation: `spring-faces`, JSF implementation, JSP/JSTL, EL, Bean Validation, ORM, thư viện layout và filter bảo mật. Bộ lọc ví dụ trên không liệt kê hết chúng.

### Gradle

```powershell
.\gradlew.bat dependencies --configuration runtimeClasspath

.\gradlew.bat dependencyInsight --dependency spring-webflow --configuration runtimeClasspath

.\gradlew.bat dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath

.\gradlew.bat dependencyInsight --dependency servlet-api --configuration runtimeClasspath
```

Nếu lỗi chỉ xuất hiện trong test, xem thêm `testRuntimeClasspath`. Nếu compile thất bại nhưng runtime report không có Servlet API, xem `compileClasspath` và dependency `compileOnly` tương ứng.

Với dự án nhiều module, thêm đường task đúng module, chẳng hạn `:web:dependencyInsight`. Không phân tích classpath của một module không được đóng gói vào ứng dụng gặp lỗi.

Gradle phân biệt dependency được yêu cầu với phiên bản được chọn và lý do chọn; `dependencyInsight` giúp truy ra constraint, platform hoặc resolution rule. Xem [Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html).

### Những điểm cần tìm trong kết quả

- Các module Spring Framework thuộc nhiều dòng hoặc lệch phiên bản ngoài chủ đích.
- `spring-webflow`, `spring-binding`, `spring-faces` bị trộn giữa các dòng phát hành.
- Thư viện tích hợp cũ kéo Spring 5 hoặc tham chiếu `javax.servlet` vào ứng dụng Spring 6/7.
- Hai họ Servlet API cùng xuất hiện ở nơi không có thiết kế cách ly rõ ràng.
- Dependency trực tiếp ghi đè phiên bản mà BOM hoặc platform đang quản lý.
- Scope test khác scope chạy ứng dụng, khiến test nạp nhầm một bộ API khác.

Một cây dependency có phiên bản được resolve duy nhất vẫn có thể không tương thích: build tool chọn được một phiên bản không có nghĩa mọi thư viện đã được biên dịch cho API của phiên bản đó.

## 6. Kiểm tra gói triển khai và nguồn lớp runtime

Với WAR, xem các JAR trong `WEB-INF/lib` và thư viện dùng chung của container. Với executable JAR, xem cấu trúc thư viện lồng theo cơ chế đóng gói của framework/build plugin.

Ví dụ liệt kê nội dung artifact, thay tên tệp bằng artifact thực tế:

```powershell
jar tf .\target\learning-web.war
```

Cây Maven/Gradle không bao gồm mọi JAR được người vận hành đặt ngoài artifact. Ngược lại, một thư viện có mặt trong cây compile có thể được khai báo `provided` và không nằm trong WAR.

### In nguồn lớp đang được nạp

Có thể dùng tiện ích Java tạm thời ở môi trường chẩn đoán để xem nguồn lớp:

```java
import java.net.URL;
import java.security.CodeSource;
import java.util.Enumeration;

public final class ClasspathProbe {
    public static void showOrigin(Class<?> type) throws Exception {
        CodeSource source = type.getProtectionDomain().getCodeSource();
        Package metadata = type.getPackage();

        System.out.println("class=" + type.getName());
        System.out.println("loader=" + type.getClassLoader());
        System.out.println("origin="
                + (source == null ? "unknown" : source.getLocation()));
        System.out.println("version="
                + (metadata == null ? null : metadata.getImplementationVersion()));

        String resource = type.getName().replace('.', '/') + ".class";
        ClassLoader loader = type.getClassLoader();
        Enumeration<URL> candidates = loader == null
                ? ClassLoader.getSystemResources(resource)
                : loader.getResources(resource);

        while (candidates.hasMoreElements()) {
            System.out.println("candidate=" + candidates.nextElement());
        }
    }
}
```

Ví dụ các lớp đáng kiểm tra trong ứng dụng Jakarta đã nạp được chúng:

```java
ClasspathProbe.showOrigin(
        org.springframework.webflow.mvc.servlet.FlowHandlerAdapter.class);
ClasspathProbe.showOrigin(
        org.springframework.web.servlet.DispatcherServlet.class);
ClasspathProbe.showOrigin(
        jakarta.servlet.http.HttpServletRequest.class);
```

Đoạn gọi cuối chỉ phù hợp với nguồn ứng dụng dùng Jakarta. Với ứng dụng javax, chọn lớp Servlet thuộc namespace của ứng dụng đó; không thêm API đối nghịch chỉ để biên dịch tiện ích.

Metadata phiên bản có thể là `null`; đây không tự là lỗi. Danh sách nhiều resource là dấu hiệu cần điều tra, còn `origin` và classloader giúp xác định lớp đã được chọn. Khi lớp không nạp được ngay từ đầu, dùng stack trace, nội dung JAR hoặc công cụ phân tích bytecode thay vì kỳ vọng tiện ích này vẫn chạy thành công.

Tránh biến tiện ích chẩn đoán thành một endpoint công khai; thông tin cần thu thập thuộc log hoặc phiên điều tra có kiểm soát của ứng dụng.

## 7. Các tình huống điển hình trong Spring Web Flow

### 7.1. Ứng dụng Jakarta còn thư viện tích hợp javax

**Biểu hiện:** khởi tạo filter, adapter hoặc view resolver thất bại do thiếu lớp `javax.servlet`.

**Bằng chứng cần tìm:** thư viện gọi trong stack trace vẫn thuộc dòng javax; container chỉ cung cấp Jakarta Servlet.

**Hướng sửa:** nâng hoặc thay thư viện tích hợp bằng dòng hỗ trợ Jakarta, đồng thời chọn Web Flow và Spring đúng thế hệ. Nếu một thư viện quan trọng chưa có bản phù hợp, phải quyết định phạm vi nâng cấp hoặc thay thành phần; thêm `javax.servlet-api` không biến implementation cũ thành Jakarta implementation.

Không phải mọi thư viện Java cũ đều cần đổi namespace. Chỉ những thành phần phụ thuộc API đã thay đổi hoặc API Spring không còn tương thích mới nằm trong ranh giới phải xử lý.

### 7.2. WAR javax được triển khai vào container Jakarta

**Biểu hiện:** servlet/filter không được tạo, lỗi kiểu không tương thích hoặc thiếu `javax.servlet`.

**Hướng sửa:** triển khai bộ ứng dụng javax vào container tương ứng, hoặc nâng đồng bộ ứng dụng và thư viện sang Jakarta. Lựa chọn phụ thuộc mục tiêu dự án; không sửa bằng cách chép nhiều bản Servlet API vào `WEB-INF/lib`.

Tomcat có công cụ hỗ trợ chuyển đổi cho một số kịch bản, nhưng kết quả vẫn cần được kiểm tra với dependency và tính năng thực tế. Công cụ chuyển package không thay thế việc giải quyết một thư viện dùng API Spring đã bị xóa hoặc thay đổi hợp đồng.

### 7.3. Cùng Jakarta nhưng sai mức Servlet API

**Biểu hiện:** lớp `jakarta.servlet` có tồn tại nhưng phát sinh lỗi phương thức hoặc implementation.

**Bằng chứng cần tìm:** code/thư viện được biên dịch với mức API cao hơn mức container thực thi. Ví dụ stack Web Flow 4.0 yêu cầu Servlet 6.1 nhưng server mới cung cấp Servlet 6.0.

**Hướng sửa:** chọn container đáp ứng baseline hoặc điều chỉnh cả stack về dòng được hỗ trợ trên container hiện có. Đổi riêng JAR API không nâng implementation của server.

### 7.4. Các module Spring bị trộn phiên bản

**Biểu hiện:** `NoSuchMethodError` ở `org.springframework.*` khi tạo context, đánh giá biểu thức hoặc dựng view.

**Bằng chứng cần tìm:** `spring-core`, `spring-beans`, `spring-context`, `spring-expression`, `spring-web` và `spring-webmvc` không được quản lý nhất quán; server có bản cũ bên ngoài artifact.

**Hướng sửa:** dùng cơ chế quản lý dependency thống nhất, bỏ override không có căn cứ và kiểm tra lại nguồn lớp. Không chọn một JAR Spring mới hơn ngẫu nhiên cho mỗi lỗi phương thức xuất hiện.

### 7.5. Startup qua nhưng validation hoặc view hỏng

**Biểu hiện:** annotation không được xử lý như kỳ vọng, thiếu validation provider, lỗi taglib/EL hoặc lỗi khi render lần đầu.

**Hướng điều tra:** API Validation và implementation có cùng thế hệ không; annotation trên model thuộc `javax.validation` hay `jakarta.validation`; thư viện view, JSP/JSTL, EL và filter có phù hợp với runtime không.

Có API trong classpath không đồng nghĩa đã có implementation cung cấp dịch vụ. Ngược lại, thêm provider nhưng giữ annotation thuộc họ API khác cũng chưa bảo đảm validator nhận đúng metadata.

Với JSF, kiểm tra thêm `spring-faces` và implementation Faces tương ứng. Với ứng dụng chỉ dùng Spring MVC, không thêm `spring-faces` như một cách chữa mọi lỗi view.

Việc nâng Web Flow 3.0 còn có thể yêu cầu thay công nghệ layout cũ; thông báo phát hành nêu việc bỏ Tiles trong sample do chưa chuyển sang Jakarta. Đây là ví dụ cho thấy migration có thể vượt quá thay import. Xem [Spring Web Flow 3.0.0 Released](https://spring.io/blog/2023/07/13/spring-web-flow-3-0-0-released/).

## 8. Quản lý dependency theo một nguồn quyết định

Nếu dùng Spring Boot, ưu tiên nền dependency management của dòng Boot đã chọn và chỉ override khi có yêu cầu cùng bằng chứng tương thích rõ ràng. Hướng dẫn migration Boot cũng yêu cầu rà soát tọa độ dependency và package khi chuyển sang Jakarta; xem [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide).

Nếu không dùng Boot, có thể dùng Spring Framework BOM để đồng bộ các module thuộc Spring Framework, rồi chọn Web Flow tương thích riêng. Spring Framework BOM không tự quyết định tất cả module của Web Flow hoặc mọi thư viện bên thứ ba.

Ví dụ Gradle Kotlin DSL sau minh họa cơ chế, chưa gán số phiên bản cụ thể:

```kotlin
val springFrameworkVersion: String by project
val springWebflowVersion: String by project

dependencies {
    implementation(platform(
        "org.springframework:spring-framework-bom:$springFrameworkVersion"
    ))
    implementation("org.springframework:spring-webmvc")
    implementation(
        "org.springframework.webflow:spring-webflow:$springWebflowVersion"
    )
}
```

Hai giá trị phải được khai báo trong cấu hình build của dự án và được chọn cùng container/JDK. Đây không phải lời khuyên dùng cùng một số phiên bản cho Spring Framework và Web Flow; hai dự án có chu kỳ và hệ số phiên bản riêng.

### Scope Servlet API phụ thuộc kiểu triển khai

- Với WAR triển khai vào container ngoài, Servlet API thường thuộc `provided` của Maven hoặc `compileOnly` của Gradle vì container cung cấp implementation/API khi chạy.
- Với ứng dụng chạy embedded server, dùng cấu hình starter/plugin và dependency của kiểu đóng gói đó để có runtime đầy đủ.
- Với test, classpath phải phản ánh nền đang kiểm tra; thư viện mock Servlet cũng cần cùng thế hệ.

Không áp dụng quy tắc “mọi Servlet dependency đều phải compileOnly” cho mọi kiểu đóng gói. Điều cần bảo đảm là thành phần cung cấp API và implementation có trách nhiệm rõ ràng, không có bản cũ vô tình che bản đúng.

### Exclusion và force phải dựa trên nguyên nhân

Exclusion có thể loại một dependency bắc cầu sai, nhưng chỉ an toàn khi thư viện kéo nó vào vẫn tương thích với API thay thế. Một thư viện dùng `javax.servlet` không trở thành thư viện Jakarta sau khi loại `javax.servlet-api` khỏi cây.

Tương tự, `force` hoặc resolution rule có thể làm báo cáo phiên bản gọn hơn nhưng không sửa được bytecode đã tham chiếu phương thức bị xóa. Sau khi dùng override, vẫn phải kiểm chứng behavior và runtime artifact.

## 9. Đừng đổi nhầm namespace XML của Spring

Package Java và namespace XML cấu hình là hai khái niệm khác nhau. Khi chuyển ứng dụng sang Jakarta, định nghĩa flow vẫn dùng namespace Spring Web Flow theo schema của framework:

```xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://www.springframework.org/schema/webflow
          https://www.springframework.org/schema/webflow/spring-webflow.xsd">
    <!-- state và transition của flow -->
</flow>
```

Không đổi `springframework.org/schema/webflow` sang một URL `jakarta` tự đặt. Ngược lại, descriptor Servlet hoặc descriptor của công nghệ EE có quy tắc schema riêng theo phiên bản; phải làm theo tài liệu tương ứng.

Một lỗi “không tìm thấy state” sau khi ứng dụng đã nạp thành công cũng không tự là lỗi Jakarta. Sau khi ranh giới classpath đã đúng, cần tiếp tục chẩn đoán flow ID, resource, event hoặc view theo bằng chứng mới.

## 10. Quy trình sửa có thể lặp lại

```text
Đọc nguyên nhân gốc
        ↓
Xác định namespace, lớp hoặc phương thức bị yêu cầu
        ↓
Ghi nhận JVM + container + dòng Spring/Web Flow
        ↓
Truy ra dependency và nguồn lớp thực tế
        ↓
Chọn bộ nền tương thích, sửa dependency/import/đóng gói cần thiết
        ↓
Build lại artifact và triển khai đúng artifact vừa tạo
        ↓
Kiểm tra startup rồi chạy hành trình đại diện
```

Sau khi sửa khai báo, build lại từ nguồn và bảo đảm tiến trình/container không còn dùng artifact cũ. Nếu container có thư viện dùng chung, phải xử lý vị trí đã xác định gây xung đột; việc làm sạch thư mục build của dự án không thay đổi thư viện ngoài đó.

Không bắt đầu bằng việc xóa toàn bộ cache Maven/Gradle. Cache hỏng là một giả thuyết riêng, cần bằng chứng như artifact sai nội dung hoặc tải lỗi; nó không giải thích được việc hai thế hệ API vốn không tương thích.

## 11. Kiểm chứng sau khi sửa

Startup thành công là một bước, chưa bao phủ các lớp chỉ được nạp khi render, bind hoặc validate. Chọn các kiểm tra liên quan đến thành phần đã thay đổi:

| Kiểm tra | Mục đích |
| --- | --- |
| Khởi động context và Web Flow infrastructure | Xác nhận các bean nền nạp được |
| Mở flow và render view đầu tiên | Kiểm tra adapter, resolver và view engine |
| Gửi form hợp lệ | Kiểm tra binding và transition chính |
| Gửi giá trị sai định dạng và dữ liệu sai validation | Kiểm tra conversion, annotation, provider và thông báo |
| Quay lại rồi sửa | Kiểm tra model/scope qua request |
| Hủy và hoàn tất | Kiểm tra outcome và tích hợp MVC sau flow |
| Gọi subflow nếu ứng dụng có | Kiểm tra hợp đồng tích hợp cha/con |
| Chạy trên kiểu JAR/WAR và container triển khai thật | Phát hiện khác biệt giữa test classpath và runtime |

Nếu đã thay đổi lớp DTO hoặc version của dữ liệu được serialize trong session, execution cũ có thể không còn khôi phục được. Cần kiểm tra chiến lược chuyển phiên/khôi phục của lần triển khai; không mặc định snapshot cũ luôn tương thích sau migration.

Test flow độc lập có thể qua vì dùng mock view và không nạp đủ Servlet/view stack. Vì vậy lỗi liên quan container hoặc taglib cần kiểm tra tại tầng tích hợp tương ứng, không chỉ chạy lại unit test action.

## 12. Bài tập chẩn đoán

Một ứng dụng đang dùng nền Spring Framework 6 và Tomcat 10.1, nhưng sau khi thêm thư viện layout cũ, mở flow báo thiếu `javax.servlet.http.HttpServletRequest`.

Hãy thực hiện về mặt thiết kế chẩn đoán:

1. Tách bean lỗi ngoài cùng khỏi nguyên nhân thiếu lớp bên trong.
2. Truy đường dependency kéo thư viện layout vào và xác định namespace mà nó yêu cầu.
3. Xem artifact để biết có JAR cũ ngoài dự kiến không.
4. Chọn bản layout tương thích hoặc thay thành phần theo hợp đồng giao diện.
5. Kiểm tra lại render, binding, validation và đường hoàn tất flow.

Sau đó xét một tình huống khác: nâng lên Web Flow 4.0 nhưng giữ Tomcat 10.1. Cả hai dùng Jakarta, tuy nhiên mức Servlet 6.0 của container chưa đáp ứng baseline Servlet 6.1 của dòng Web Flow này. Cần đối chiếu nền phiên bản trước khi kết luận rằng mọi lỗi namespace đã được giải quyết.

Nguyên tắc chẩn đoán là xác định **thư viện nào yêu cầu API nào, API nào thực sự được cung cấp và lớp nào đã được nạp**. Khi ba câu trả lời khớp nhau, việc sửa dependency mới có căn cứ và hành trình Spring Web Flow mới được kiểm chứng trên đúng nền chạy.