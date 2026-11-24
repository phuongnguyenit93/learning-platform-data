# Kiểm tra classpath và tránh xung đột web stack trong Spring Cloud Gateway

Khi khởi tạo **SPRING_CLOUD_GATEWAY**, một lỗi dễ gặp là ứng dụng có đầy đủ dependency nhưng Gateway không khởi động hoặc không nhận route. Nguyên nhân thường nằm ở **classpath**: dự án dự định chạy Gateway theo mô hình reactive nhưng vô tình kéo thêm Spring MVC, hoặc ngược lại chọn Gateway Server MVC mà lại áp dụng cấu hình và API dành cho WebFlux.

Bài này thuộc chương **Khởi tạo**. Mục tiêu là tự xác định web stack mà ứng dụng đang dùng, phát hiện dependency gây xung đột và kiểm chứng rằng Gateway thật sự có thể nhận, xử lý và chuyển tiếp request trước khi xây dựng các tính năng route predicate, filter chain, sửa path/header, khám phá dịch vụ, xác thực, rate limiting, circuit breaker, retry, TLS và quan sát request.

## 1. Classpath quyết định điều gì khi ứng dụng khởi động?

**Classpath** là tập class và thư viện có mặt khi JVM nạp ứng dụng. Với Spring Boot, classpath tác động đến **auto-configuration** và việc xác định loại ứng dụng web. Hai thành phần đáng chú ý:

- **Servlet stack**: thường dùng Spring MVC, `DispatcherServlet` và một servlet container như Tomcat hoặc Jetty. Gateway tương ứng là **Spring Cloud Gateway Server MVC**.
- **Reactive stack**: thường dùng Spring WebFlux, `DispatcherHandler`, Reactive Streams và HTTP server phù hợp, phổ biến là Reactor Netty. Gateway tương ứng là **Spring Cloud Gateway Server WebFlux**.

Spring Boot có thể suy ra loại ứng dụng web từ các class có mặt:

| Dấu hiệu trên classpath | Kết quả mặc định thường gặp | Ý nghĩa |
|---|---|---|
| Có WebFlux, không có Spring MVC | `REACTIVE` | Boot có thể tạo reactive web application context |
| Có Spring MVC (kể cả khi đồng thời có WebFlux) | `SERVLET` | Boot thường ưu tiên Spring MVC khi cả hai framework hiện diện |
| Không có các thành phần web server cần thiết | `NONE` hoặc lỗi do thiếu dependency | Ứng dụng không có HTTP gateway hoạt động như mong đợi |
| Có cấu hình `spring.main.web-application-type` | Theo giá trị được ép nếu điều kiện khởi tạo thỏa mãn | Cần kiểm chứng runtime; cấu hình ép không sửa dependency sai |

Trong ứng dụng thực tế còn có auto-configuration, exclusion và cấu hình riêng tác động đến kết quả. Vì vậy, **sự có mặt của một JAR chưa đủ để kết luận Gateway đang chạy theo stack nào**. Hãy kết hợp dependency tree, log khởi động và loại application context thực tế.

Ví dụ, một ứng dụng Spring MVC có thể sử dụng `WebClient` từ Spring WebFlux để gọi HTTP bên ngoài; điều đó **không tự biến server Servlet thành server Reactive**. Ngược lại, thư viện Reactor Netty xuất hiện vì HTTP client cũng chưa chứng minh server Gateway đang chạy bằng Reactor Netty.

## 2. Chọn đúng biến thể Gateway ngay từ đầu

Spring Cloud Gateway có hai hướng triển khai server phổ biến; các tên starter và namespace cấu hình cụ thể phụ thuộc vào **dòng phiên bản Gateway/Spring Cloud**.

| Câu hỏi | Gateway Server WebFlux | Gateway Server MVC |
|---|---|---|
| Web stack | Reactive, nền tảng Spring WebFlux | Servlet, nền tảng Spring Web MVC |
| Kiểu xử lý | Chuỗi reactive, non-blocking khi các thành phần liên quan hỗ trợ | Servlet/WebMvc.fn và mô hình xử lý của Servlet |
| Thành phần nhận HTTP | Reactive web server, thường là Reactor Netty | Servlet container, thường là Tomcat |
| Starter ở một số dòng phát hành mới | `spring-cloud-starter-gateway-server-webflux` | `spring-cloud-starter-gateway-server-webmvc` |
| Tên starter gặp ở các dòng cũ hơn | `spring-cloud-starter-gateway` | `spring-cloud-starter-gateway-mvc` |
| Điều cần tránh | Để Spring MVC vô tình thay đổi loại web application | Sao chép DSL, filter hoặc cấu hình riêng cho WebFlux |
| Thường phù hợp khi | Dự án chủ động vận hành Gateway reactive và dùng các tích hợp phù hợp | Dự án cần triển khai Gateway theo Servlet stack |

**Chọn một biến thể server làm nền tảng cho một ứng dụng Gateway.** Không khai báo đồng thời hai starter Gateway server chỉ để “hỗ trợ cả hai”. Việc trộn WebFlux và MVC gây nhầm lẫn về cơ chế route, bộ lọc, bảo mật và auto-configuration.

### Ví dụ dependency Maven

Với một **dòng phát hành có hỗ trợ tên starter mới**, ứng dụng Gateway WebFlux có thể khai báo:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
</dependencies>
~~~

Nếu chủ đích là Gateway Server MVC, **thay** dependency trên bằng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webmvc</artifactId>
    </dependency>
</dependencies>
~~~

Đây là các **phương án thay thế**, không phải hai khối cần ghép lại. Với release train cũ, dùng tên starter tương ứng được tài liệu **đúng phiên bản** quy định. Phiên bản của Gateway starter thường được quản lý bởi **Spring Cloud BOM** tương thích với Spring Boot; không tùy tiện gán version độc lập cho nhiều artifact Spring Cloud.

Ví dụ ở Gradle Kotlin DSL cũng chọn **một** trong hai:

~~~kotlin
dependencies {
    // Gateway Server WebFlux ở dòng phát hành hỗ trợ starter này
    implementation("org.springframework.cloud:spring-cloud-starter-gateway-server-webflux")

    // Nếu chọn Server MVC, bỏ dòng WebFlux phía trên
    // và dùng starter MVC tương ứng:
    // implementation("org.springframework.cloud:spring-cloud-starter-gateway-server-webmvc")
}
~~~

Các khối trên chỉ minh họa **phần dependency Gateway**, chưa phải một dự án Spring Boot hoàn chỉnh. Khi tạo dự án thật cần cấu hình Spring Boot plugin/parent, dependency management hoặc BOM và JDK tương thích; đối chiếu các phiên bản với tài liệu chính thức của đúng release train.

## 3. Tại sao thêm `spring-boot-starter-web` có thể làm Gateway WebFlux lỗi?

Xét dự án ban đầu chỉ có Gateway Server WebFlux. Sau đó, một thành viên thêm `spring-boot-starter-web` vì nghĩ mọi REST API đều cần starter này:

~~~xml
<!-- Không thêm vào ứng dụng Gateway WebFlux chỉ theo thói quen -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Starter này thường đưa **Spring MVC** (`spring-webmvc`) và các thư viện Servlet vào classpath. Nếu Boot phát hiện cả Spring MVC và WebFlux, nó **thường chọn `SERVLET` mặc định**. Trong khi đó, Gateway Server WebFlux cần môi trường reactive. Tùy phiên bản, ứng dụng có thể xuất hiện thông báo đại ý “Spring MVC found on classpath; incompatible with Spring Cloud Gateway”, hoặc lỗi bean/auto-configuration khác liên quan đến web stack.

Nguồn gốc của `spring-webmvc` không nhất thiết nằm trong dependency khai báo trực tiếp. Nó có thể xuất hiện qua một starter của thư viện dùng chung, module nội bộ, công cụ tạo API docs hoặc dependency bắc cầu.

~~~mermaid
flowchart TD
    A["Ứng dụng Gateway Server WebFlux"] --> B["Thêm dependency trực tiếp hoặc bắc cầu"]
    B --> C{"Classpath chứa Spring MVC?"}
    C -->|Không| D["Boot có thể chọn REACTIVE"]
    C -->|Có| E["Boot thường ưu tiên SERVLET"]
    D --> F["Xác nhận reactive context và route thật"]
    E --> G["Gateway WebFlux có nguy cơ không khởi tạo"]
    G --> H["Tìm nhánh dependency kéo spring-webmvc"]
    H --> I["Loại bỏ hoặc thay đúng dependency"]
    I --> F
~~~

**Không phải cứ có cả `spring-webflux` và `spring-webmvc` trong JVM là chắc chắn sai.** Cách kết hợp này có thể hợp lệ khi ứng dụng chủ đích là Servlet và dùng reactive HTTP client. Xung đột xuất hiện khi **stack thực sự được chọn không khớp yêu cầu của Gateway server đang dùng**, hoặc khi một nhóm áp dụng cấu hình/API của nhầm biến thể.

## 4. Kiểm tra classpath bằng Maven

Trước tiên, chạy lệnh tại **module thực sự tạo ứng dụng Gateway**, không chỉ ở thư mục gốc của dự án nhiều module.

~~~bash
# Hiển thị cây dependency và đường dẫn kéo thư viện vào ứng dụng
./mvnw dependency:tree

# Có thể tập trung kiểm tra các artifact Spring chính
./mvnw dependency:tree -Dincludes=org.springframework:*
~~~

Ở Windows, dùng `mvnw.cmd` thay `./mvnw` nếu dự án có Maven Wrapper. Nếu không có Wrapper, dùng Maven được cài sẵn (`mvn`).

Từ kết quả, tìm các thành phần:

- `spring-cloud-starter-gateway...`: starter Gateway nào đang được chọn, WebFlux hay MVC?
- `spring-webmvc`, `spring-boot-starter-web`: dấu hiệu Spring MVC có mặt.
- `spring-webflux`, `spring-boot-starter-webflux`: các thành phần WebFlux.
- `spring-boot-starter-tomcat` hoặc servlet container khác: xác định có dependency Servlet server hay không.
- `reactor-netty-http` hoặc thư viện server khác: kiểm tra thành phần reactive; đừng kết luận chỉ từ một JAR.
- `spring-cloud-dependencies` và dependency đã resolve: đối chiếu release train, Boot và Gateway, tránh version lệch nhau.

**Mẹo đọc cây**: nếu thấy `spring-webmvc`, lần ngược các nhánh cha để xác định dependency nào đã kéo nó vào. Chẳng hạn mô hình minh họa:

~~~text
gateway-app
+-- spring-cloud-starter-gateway-server-webflux
\-- shared-web-starter
    \-- spring-boot-starter-web
        \-- spring-webmvc
~~~

Khi đó điểm cần xử lý là `shared-web-starter` hoặc quan hệ dependency của nó, không phải xóa bừa JAR `spring-webmvc` trong cache.

### Kiểm tra Maven dependency management

Nếu `pom.xml` khai báo dependency nhưng Gateway vẫn không đúng version, đọc **effective POM** hoặc cây dependency để biết phiên bản đã resolve. BOM của Spring Cloud quản lý các artifact trong cùng release train; nên đối chiếu với bảng tương thích Spring Boot–Spring Cloud của **dòng đang chạy**. Không ép version một starter riêng để chữa lỗi web stack nếu nguyên nhân là trộn Servlet/Reactive.

## 5. Kiểm tra classpath bằng Gradle

Với Gradle, cần nhìn vào **runtimeClasspath** của module chạy Gateway; `compileClasspath` có thể không phản ánh đầy đủ dependency lúc thực thi.

~~~bash
# Xem toàn bộ dependency được chọn cho runtime
./gradlew dependencies --configuration runtimeClasspath

# Tìm vì sao spring-webmvc xuất hiện và version nào được chọn
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath

# Truy ngược starter web nếu có
./gradlew dependencyInsight --dependency spring-boot-starter-web --configuration runtimeClasspath

# Xác định starter Gateway và những phiên bản được resolve
./gradlew dependencyInsight --dependency spring-cloud-starter-gateway --configuration runtimeClasspath
~~~

Ở Windows, có thể dùng `gradlew.bat`. Đối với Gradle nhiều module, chỉ định task thuộc module đích, ví dụ `:gateway-app:dependencyInsight`. Với build có cấu hình riêng, lựa chọn configuration cần phù hợp với artifact sẽ chạy. Dependency thuộc `testRuntimeClasspath` **không tự đồng nghĩa** với xung đột production runtime.

Khi Gradle báo một version được chọn do conflict resolution hoặc constraint, cần xác minh BOM/plugin đang quản lý dependency nào. Đừng xóa constraint hoặc thêm `force` trước khi kiểm tra tương thích của release train.

## 6. Xử lý xung đột: sửa từ nguyên nhân

### Trường hợp A — Dự án cần Gateway Server WebFlux

1. Xác nhận dependency Gateway thực sự thuộc biến thể **Server WebFlux** của phiên bản hiện tại.
2. Tìm `spring-boot-starter-web`/`spring-webmvc` được khai báo trực tiếp hoặc kéo vào từ dependency khác.
3. Bỏ starter Servlet không cần thiết hoặc **thay** thư viện dùng chung bằng biến thể không ép MVC.
4. Nếu thư viện vẫn cần cho nghiệp vụ, sử dụng exclusion **đúng nhánh gây lỗi**, kiểm tra xem nó có còn hoạt động khi thiếu MVC không.
5. Chạy lại dependency tree và khởi động Gateway; xác nhận reactive context và route hoạt động.

Ví dụ **minh họa** Maven: thư viện `com.example:legacy-client` được xác nhận chỉ dùng phần HTTP client, nhưng nó kéo nhầm `spring-boot-starter-web`.

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>legacy-client</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Trong Gradle Kotlin DSL, exclusion tương ứng:

~~~kotlin
implementation("com.example:legacy-client:1.0.0") {
    exclude(group = "org.springframework.boot", module = "spring-boot-starter-web")
}
~~~

**Đây không phải cách sửa mặc định cho mọi thư viện.** Nếu `legacy-client` thực sự cần `DispatcherServlet` hoặc API Servlet, exclusion có thể làm lỗi xuất hiện ở runtime; phải thay thiết kế hoặc tách module. Đặc biệt, exclusion ở một nhánh không loại được `spring-webmvc` nếu nó còn được kéo vào từ nhánh khác. Luôn kiểm tra cây dependency **sau** khi sửa.

### Trường hợp B — Dự án cần Gateway Server MVC

Giữ starter **Server MVC** phù hợp với release train và Servlet web stack. Không thay starter MVC bằng WebFlux chỉ vì tài liệu trên mạng có route/filter tương tự. Xem API, route predicate và filter của **Gateway Server MVC**; một filter viết cho reactive exchange không thể tự dùng trong Servlet filter chain.

Có thể dùng `WebClient` cho outbound HTTP từ một ứng dụng Servlet khi thực sự cần, nhưng vẫn phải xác nhận Boot tạo **Servlet web context** và các route Gateway MVC được khởi tạo đúng.

### Trường hợp C — Muốn ép `spring.main.web-application-type=reactive`

Trong một số phiên bản, có thể dùng:

~~~yaml
spring:
  main:
    web-application-type: reactive
~~~

Thuộc tính này **chỉ ép Boot chọn loại ứng dụng web**, không xóa `spring-webmvc` khỏi classpath và không biến controller hoặc thư viện dựa trên Servlet thành thành phần reactive. Nó cũng không thay được Gateway MVC thành Gateway WebFlux.

Chỉ dùng phương án này khi đã xác định chủ đích triển khai là reactive, hiểu đầy đủ nguồn dependency và đã kiểm tra các thành phần tích hợp. Đối với dự án mới, **loại bỏ dependency gây nhầm stack** thường rõ ràng và dễ bảo trì hơn.

Tương tự, `web-application-type: none` không phải cách xử lý cho Gateway HTTP vì Boot sẽ không tạo web server nhận request như mong đợi.

## 7. Kiểm tra web stack thực sự lúc chạy

Dependency tree cho biết thư viện có mặt; bước tiếp theo là chứng minh **ứng dụng đã tạo đúng server**.

### Bước 1 — Đọc startup log và application context

Khi khởi động, quan sát web server, loại application context và các thông báo auto-configuration. Thường gặp:

- **Server WebFlux**: một lớp context dạng reactive web server, ví dụ `ReactiveWebServerApplicationContext`; server HTTP mặc định thường là Reactor Netty.
- **Server MVC**: một lớp context dạng servlet web server, ví dụ `ServletWebServerApplicationContext`; server HTTP thường là Tomcat, Jetty hoặc loại servlet container phù hợp.

Không chỉ dựa vào tên `Netty` hoặc `Tomcat`: tùy cách cấu hình, WebFlux có thể vận hành trên server khác; thông tin context và route đã đăng ký đáng tin hơn.

Có thể tạm thời in class của application context để chẩn đoán:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class WebStackDiagnostics {

    @Bean
    ApplicationRunner showWebContext(ApplicationContext context) {
        return args -> System.out.println(
            "Gateway ApplicationContext: " + context.getClass().getName()
        );
    }
}
~~~

Đoạn này dùng để **quan sát**, không để quyết định stack bằng chuỗi tên class. Bỏ log tạm sau khi xử lý, hoặc thay bằng kiểm tra tự động phù hợp với dự án.

### Bước 2 — Thử route thật qua một downstream giả lập

Ví dụ dưới đây minh họa cấu hình route thường dùng ở **một số dòng Gateway Server WebFlux 4.x**. Tên namespace và định dạng route có thể khác ở các dòng/biến thể khác; hãy kiểm tra tài liệu phiên bản bạn đang dùng:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: inventory
          uri: http://localhost:9090
          predicates:
            - Path=/api/inventory/**
          filters:
            - StripPrefix=1
~~~

Giả định một downstream đang chạy ở cổng **9090** và trả HTTP 200 cho `GET /inventory/items`. Sau khi khởi động Gateway ở cổng **8080**, gọi:

~~~bash
curl -i http://localhost:8080/api/inventory/items
~~~

Kết quả mong đợi: Gateway match predicate `Path`, `StripPrefix=1` bỏ phân đoạn `api`, rồi downstream nhận `GET /inventory/items`. Nếu gateway không có route, có thể nhận **404**; nếu route có nhưng downstream không truy cập được, có thể gặp **5xx**. Mã trả về cụ thể còn phụ thuộc filter, exception handler và phiên bản, nên phải đối chiếu log thay vì đoán duy nhất từ status code.

Với **Gateway Server MVC**, dùng cấu hình/DSL route tương ứng MVC và thực hiện cùng phép thử đầu vào/đầu ra. Không sao chép namespace YAML của WebFlux vào một ứng dụng MVC rồi mặc định rằng route sẽ được nạp.

### Bước 3 — Kiểm tra cả request lỗi

Một gateway hợp lệ còn cần xử lý tình huống sai đường dẫn, downstream ngừng hoạt động và bảo mật bị từ chối. Tùy chức năng đã bật, xác minh:

| Hành vi | Điểm quan sát |
|---|---|
| Route predicate không khớp | Không chuyển request sang nhầm dịch vụ; hành vi 404 được xử lý đúng |
| Filter sửa path/header | Downstream nhận đúng path/header; không vô tình lộ header nhạy cảm |
| Xác thực | Request thiếu/sai token bị chặn tại lớp thích hợp |
| Rate limiting | Request vượt ngưỡng được xử lý theo chính sách, thường là HTTP 429 |
| Circuit breaker và retry | Không tạo retry vô hạn; fallback/cơ chế lỗi hoạt động dự kiến |
| Service discovery | Tên dịch vụ được giải quyết qua cơ chế discovery/load balancer đã cấu hình |
| TLS | Kiểm tra HTTPS, trust/certificate và cách kết nối đến downstream |
| Logs/metrics/tracing | Có dữ liệu quan sát route, latency, lỗi và request flow theo phiên bản đang dùng |

Những kiểm tra này chỉ áp dụng khi tính năng đã được cấu hình. Bài này tập trung vào **nền web stack đúng**, là điều kiện cần trước khi triển khai các tích hợp.

## 8. Những lỗi thường gặp và cách khoanh vùng

| Triệu chứng | Khả năng cần kiểm tra | Hướng xử lý |
|---|---|---|
| Khởi động báo MVC không tương thích với Gateway | Đang dùng **WebFlux Gateway** nhưng classpath có Spring MVC | Truy ngược `spring-webmvc`, bỏ/thay dependency Servlet không cần thiết |
| Có `spring-webflux` nhưng Boot vẫn tạo servlet context | Classpath đồng thời có `spring-webmvc` | Xác định chủ đích MVC hay WebFlux; WebFlux HTTP client không có nghĩa server reactive |
| Ứng dụng chạy nhưng không đăng ký route | Nhầm biến thể Gateway hoặc namespace cấu hình; auto-configuration không được kích hoạt | Kiểm tra starter, cấu hình route và log theo đúng phiên bản |
| Lỗi `ClassNotFoundException`, `NoSuchMethodError`, thiếu bean Gateway | Version Spring Boot/Spring Cloud/Gateway không tương thích hoặc classpath thiếu dependency | Kiểm tra BOM và dependency đã resolve; khôi phục tập phiên bản tương thích |
| Gateway MVC khởi động nhưng copy filter từ WebFlux không dùng được | API/filter của hai biến thể khác nhau | Viết lại theo API của Gateway Server MVC |
| Gateway WebFlux chạy nhưng gặp lỗi khi xử lý request | Thành phần yêu cầu Servlet hoặc thao tác chặn (blocking) trên event loop | Xác định dependency/stack và kiểm tra nơi thực hiện I/O blocking; chuyển sang API phù hợp |
| Chạy local được, chạy bản đóng gói lỗi | Runtime classpath, profile, scope hoặc dependency trong artifact khác môi trường IDE | Kiểm tra dependency và log của **đúng artifact triển khai** |

**Đừng quy ngay mọi HTTP 404/5xx thành xung đột stack.** Chỉ kết luận khi tìm thấy bằng chứng từ dependency tree, context, cấu hình route và log. Lỗi route, service discovery hay security cũng có thể tạo triệu chứng tương tự.

## 9. Quy trình chẩn đoán từ đầu đến cuối

Tình huống thực hành: nhóm tạo một API Gateway reactive để điều phối `/api/orders/**`, sau đó tích hợp một starter dùng chung và ứng dụng bắt đầu báo lỗi khi khởi động.

1. **Nêu dự định rõ ràng:** đây là **Gateway Server WebFlux**, cần reactive server, không có nhu cầu chạy Spring MVC controller.
2. **Đọc build file:** xác nhận starter Gateway đã chọn và phiên bản Spring Boot/Spring Cloud BOM. Không dùng lẫn starter Gateway MVC.
3. **Kiểm tra runtime dependency:** chạy `dependency:tree` hoặc `dependencyInsight`, tìm `spring-webmvc` và nhánh bắc cầu xuất phát từ starter dùng chung.
4. **Sửa quan hệ dependency:** loại hoặc thay starter làm phát sinh Servlet API nếu nó không phục vụ Gateway; tránh exclusion nếu thư viện thực sự phụ thuộc MVC.
5. **Kiểm tra sau sửa:** chạy lại cây dependency; xây và khởi động ứng dụng theo quy trình dự án, quan sát context reactive và route được đăng ký.
6. **Thử request:** gọi route đến downstream giả lập, xác minh path/header, mã thành công và mã lỗi theo tình huống.
7. **Ghi quyết định:** lưu artifact Gateway, phiên bản đã resolve, biến thể, nguyên nhân xung đột, dependency đã điều chỉnh và bằng chứng smoke test.

Nếu nhóm chủ đích triển khai Gateway trên Servlet, bắt đầu quy trình trên bằng **Gateway Server MVC**, xác nhận servlet context và thay các ví dụ/DSL reactive bằng tài liệu MVC tương ứng.

~~~mermaid
flowchart TD
    A["Khởi động Gateway gặp lỗi hoặc route không hoạt động"] --> B["Xác nhận WebFlux hay MVC đã chọn"]
    B --> C["Kiểm tra Maven/Gradle runtime classpath"]
    C --> D{"Starter và stack có khớp?"}
    D -->|Không| E["Tìm dependency trực tiếp/bắc cầu gây lệch"]
    E --> F["Bỏ, thay hoặc exclude có kiểm chứng"]
    D -->|Có| G["Xác nhận Boot/Cloud BOM và cấu hình route"]
    F --> G
    G --> H["Khởi động và đọc application context"]
    H --> I["Smoke test route với downstream"]
    I --> J{"Kết quả đạt yêu cầu?"}
    J -->|Chưa| C
    J -->|Đạt| K["Ghi lại phiên bản, dependency và kết quả"]
~~~

## 10. Checklist trước khi phát triển Gateway

- [ ] Đã chọn **Server WebFlux** hoặc **Server MVC** cho ứng dụng.
- [ ] Đã xác nhận **starter Gateway đúng tên của release train đang sử dụng**.
- [ ] Đã đối chiếu phiên bản **JDK, Spring Boot, Spring Cloud BOM và Gateway**.
- [ ] Đã kiểm tra **runtimeClasspath** hoặc Maven dependency tree của module thực chạy.
- [ ] Đã tìm nguồn của `spring-webmvc`/`spring-boot-starter-web` nếu dự án cần Gateway WebFlux.
- [ ] Đã xác nhận không vô tình dùng đồng thời hai starter Gateway server.
- [ ] Đã giải thích được lý do có `spring-webflux` khi dự án chủ đích là Servlet.
- [ ] Đã xem startup log và xác nhận loại **application context** phù hợp.
- [ ] Đã xác minh route predicate, filter path/header và downstream bằng request thật.
- [ ] Đã thực hiện tối thiểu một tình huống lỗi; các cấu hình security/TLS/rate limiting/discovery được kiểm tra nếu có.
- [ ] Đã ghi lại các dependency exclusion hoặc quyết định chọn web stack để nhóm bảo trì hiểu rõ.

## Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — chọn đúng **phiên bản** và mục **Server WebFlux** hoặc **Server MVC**.
- [Spring Cloud project](https://spring.io/projects/spring-cloud) — release train và thông tin tương thích với Spring Boot.
- [Spring Boot Reference Documentation](https://docs.spring.io/spring-boot/reference/) — web applications, auto-configuration và dependency management.
- [Spring Framework — Web on Reactive Stack](https://docs.spring.io/spring-framework/reference/web/webflux.html) — cơ chế WebFlux và mối quan hệ với Servlet stack.

**Ghi nhớ:** Gateway chỉ hoạt động ổn định khi **biến thể Gateway, dependency runtime, loại Spring Boot web application và cấu hình route** thống nhất với nhau. Hãy xác nhận classpath và request flow ngay khi khởi tạo, trước khi bổ sung các filter và cơ chế an toàn cho microservices.
