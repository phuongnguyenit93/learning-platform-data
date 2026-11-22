# Đánh giá khả năng hỗ trợ Servlet hoặc Reactive của từng máy chủ theo phiên bản

## 1. Mục tiêu và phạm vi

Một dự án Spring Boot có thể phục vụ HTTP bằng **Spring MVC (Servlet stack)** hoặc **Spring WebFlux (reactive stack)**. Chọn máy chủ không chỉ là chọn Tomcat, Jetty, Undertow hay Netty: cần kiểm tra đồng thời phiên bản Spring Boot, phiên bản máy chủ, mức Jakarta Servlet được hỗ trợ, mô hình xử lý và dependency thực tế.

Bài học này đưa ra cách đánh giá có căn cứ, tập trung vào các dòng đại diện **Spring Boot 2.7, 3.2, 3.5 và 4.0/4.1**, cùng những khác biệt khi nâng cấp. Số phiên bản máy chủ trong bảng là **dòng phiên bản được Spring Boot tích hợp hoặc hỗ trợ**, không phải cam kết rằng mọi bản vá thuộc dòng đó đều tương thích với mọi bản Spring Boot. Luôn dùng BOM/parent và tài liệu của **đúng phiên bản Boot đang chạy**.

Các câu hỏi cần trả lời khi thẩm định một tổ hợp:

1. Máy chủ có cung cấp **Servlet API** đủ phiên bản cho Spring MVC không?
2. Nó có thể chạy **Spring WebFlux** thông qua cơ chế I/O không chặn hoặc adapter tương ứng không?
3. Spring Boot đang dùng có **starter và auto-configuration** chính thức cho máy chủ đó không?
4. Java, namespace **javax.servlet / jakarta.servlet**, thư viện và môi trường triển khai có đồng bộ không?
5. Phiên bản máy chủ thực tế được Maven/Gradle giải quyết có khớp với dependency management và yêu cầu bảo mật không?

## 2. Phân biệt máy chủ HTTP, Servlet và Reactive

### Servlet stack: Spring MVC

Trong Spring MVC, HTTP request đi qua **Servlet container**, Filter chain và DispatcherServlet. Controller có thể làm việc với API Servlet khi cần. Tomcat, Jetty và (đối với các dòng Boot còn hỗ trợ) Undertow là những Servlet container nhúng quen thuộc.

Servlet là một đặc tả API, còn Tomcat/Jetty/Undertow là các hiện thực cụ thể. Một máy chủ có thể hỗ trợ HTTP nhưng không phải Servlet container. Vì vậy **Reactor Netty không được dùng để chạy Spring MVC theo Servlet stack**.

### Reactive stack: Spring WebFlux

Spring WebFlux sử dụng **Reactive Streams**, Publisher và API xử lý HTTP không chặn. Với Spring Boot, **Reactor Netty** là HTTP server mặc định của starter WebFlux. WebFlux cũng có thể chạy trên **Tomcat hoặc Jetty** thông qua cầu nối Servlet non-blocking I/O. Trong Spring Boot 2.x/3.x, Undertow cũng là một lựa chọn được hỗ trợ; điều này thay đổi ở Boot 4.x.

Điểm cần phân biệt: **WebFlux chạy trên Tomcat không biến Tomcat thành Reactor Netty** và cũng không có nghĩa ứng dụng dùng Servlet MVC. WebFlux vẫn sử dụng mô hình lập trình reactive, còn Tomcat là runtime phía dưới.

**Có khả năng I/O không chặn** không có nghĩa toàn bộ ứng dụng là non-blocking. Một WebFlux controller gọi JDBC đồng bộ hoặc chặn trên event loop vẫn có thể gây nghẽn.

### Ba lớp tương thích độc lập

| Lớp | Cần kiểm tra | Ví dụ |
|---|---|---|
| Framework/Boot | Spring MVC hay WebFlux; starter/auto-configuration được hỗ trợ | Boot 3.5 có starter Undertow; Boot 4.x không |
| Runtime | Tomcat, Jetty, Undertow, Reactor Netty và phiên bản chính xác | Tomcat 10.1 khác Tomcat 11.0 |
| API/nền tảng | Java, Servlet specification, javax/jakarta và dependency | Boot 4.x dùng baseline Servlet 6.1 |

Nếu một trong ba lớp lệch phiên bản, việc máy chủ có thể mở cổng HTTP vẫn không bảo đảm ứng dụng khởi động hoặc vận hành đúng.

## 3. Ma trận máy chủ nhúng theo dòng Spring Boot

Bảng dưới đây tổng hợp từ **System Requirements** và **Embedded Web Servers** của Spring Boot. Dòng **Boot 3.0/3.1** có khác biệt trong các bản phát hành đầu của 3.x; không suy từ bảng Boot 3.2/3.5 để kết luận cho 3.0/3.1.

| Dòng Spring Boot | Java tối thiểu | Tomcat cho Servlet | Jetty cho Servlet | Undertow cho Servlet | Server mặc định của WebFlux |
|---|---:|---|---|---|---|
| **2.7.x** | 8 | **9.0**, Servlet **4.0** | **9.4**, Servlet **3.1**; hoặc **10.0**, Servlet **4.0** | **2.0**, Servlet **4.0** | **Reactor Netty** |
| **3.2.x** | 17 | **10.1**, Servlet **6.0** | **12.0**, Servlet **6.0** | **2.3**, Servlet **6.0** | **Reactor Netty** |
| **3.5.x** | 17 | **10.1**, Servlet **6.0** | **12.0**, Servlet **6.0** | **2.3**, Servlet **6.0** | **Reactor Netty** |
| **4.0.x** | 17 | **11.0.x**, Servlet **6.1** | **12.1.x**, Servlet **6.1** | **Không hỗ trợ nhúng trong Boot 4** | **Reactor Netty** |
| **4.1.x** | 17 | **11.0.x**, Servlet **6.1** | **12.1.x**, Servlet **6.1** | **Không hỗ trợ nhúng trong Boot 4** | **Reactor Netty** |

**Cách đọc đúng bảng:**

- Cột Servlet là **phiên bản đặc tả Servlet** gắn với máy chủ theo tài liệu Boot, không phải phiên bản Spring Framework.
- Reactor Netty là máy chủ HTTP non-Servlet, vì vậy cột này **không có Servlet specification**.
- WebFlux không bị giới hạn vào Reactor Netty: nó cũng chạy trên Tomcat và Jetty được hỗ trợ, và trên Undertow trong các dòng Boot mà starter Undertow còn tồn tại.
- Với **Boot 2.7**, namespace ứng dụng là **javax.servlet**. Từ **Boot 3.x**, ứng dụng chuyển sang **jakarta.servlet**. Chỉ đổi phiên bản máy chủ mà giữ import cũ có thể gây lỗi class loading hoặc compile.
- **Boot 4.x yêu cầu Servlet 6.1** cho servlet stack; Undertow không đạt baseline đó trong phạm vi hỗ trợ chính thức của Boot 4, nên starter Undertow và khả năng embedded Undertow đã bị loại bỏ.
- Đối với **Boot 3.0/3.1**, hãy đọc chính xác trang yêu cầu hệ thống, release note và dependency management của bản vá đang triển khai; không coi mọi bản 3.x có cùng ma trận máy chủ.

**Nguồn phiên bản chính thức:**
- Boot 2.7.18: https://docs.spring.io/spring-boot/docs/2.7.x/reference/htmlsingle/
- Boot 3.2.x: https://docs.spring.io/spring-boot/docs/3.2.12/reference/htmlsingle/
- Boot 3.5.x: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Boot 4.0.x: https://docs.spring.io/spring-boot/4.0/system-requirements.html
- Boot 4.1.x: https://docs.spring.io/spring-boot/system-requirements.html

Các liên kết theo nhánh có thể cập nhật phiên bản vá mới; khi cần tái lập chính xác môi trường, hãy tham chiếu bản tài liệu gắn với phiên bản vá của ứng dụng.

## 4. Ma trận lựa chọn Servlet hoặc WebFlux theo từng máy chủ

Ký hiệu trong bảng: **Có** = Boot cung cấp tích hợp máy chủ tương ứng; **Không** = không đúng loại runtime hoặc đã không còn được Boot hỗ trợ chính thức. Một ô **Có** vẫn phải dùng đúng phiên bản máy chủ được Boot quản lý.

| Máy chủ | Spring MVC / Servlet trên Boot 2.7 | Spring WebFlux trên Boot 2.7 | Spring MVC / Servlet trên Boot 3.5 | Spring WebFlux trên Boot 3.5 | Spring MVC / Servlet trên Boot 4.x | Spring WebFlux trên Boot 4.x |
|---|---|---|---|---|---|---|
| **Tomcat** | Có | Có qua non-blocking Servlet adapter | Có | Có qua adapter | Có | Có qua adapter |
| **Jetty** | Có | Có qua non-blocking Servlet adapter | Có | Có qua adapter | Có | Có qua adapter |
| **Undertow** | Có | Có qua tích hợp reactive của Spring | Có | Có qua tích hợp reactive của Spring | **Không** | **Không** |
| **Reactor Netty** | **Không** | Có, mặc định | **Không** | Có, mặc định | **Không** | Có, mặc định |

Từ bảng này có thể rút ra quy tắc quyết định:

- Ứng dụng **MVC + JDBC/JPA đồng bộ**: ưu tiên Tomcat mặc định; Jetty là lựa chọn thay thế tương thích, Undertow chỉ khi Boot còn hỗ trợ.
- Ứng dụng **WebFlux non-blocking**: Reactor Netty là lựa chọn mặc định; Tomcat/Jetty vẫn hợp lệ nếu có nhu cầu chuẩn hóa hạ tầng.
- Ứng dụng đang dùng **Undertow** và dự định chuyển sang **Boot 4**: cần lên kế hoạch đổi HTTP server trước khi nâng cấp.
- **Netty tự thân** có event loop và API I/O riêng; nó không hiện thực Servlet API để chạy DispatcherServlet theo mô hình Spring MVC.

## 5. Đánh giá riêng từng máy chủ

### 5.1. Apache Tomcat

**Spring MVC:** Tomcat là server nhúng mặc định của **spring-boot-starter-web** trong Boot 2.x/3.x; các dòng Boot 4.x có starter web MVC và tiếp tục sử dụng Tomcat mặc định.

**Spring WebFlux:** có thể sử dụng Tomcat qua adapter không chặn của Spring WebFlux, nhưng cần loại server Reactor Netty mặc định trong dependency của ứng dụng reactive rồi đưa Tomcat starter vào.

**Mốc tương thích quan trọng:**

- Boot 2.7: Tomcat 9.0, Servlet 4.0, javax.servlet.
- Boot 3.2/3.5: Tomcat 10.1, Servlet 6.0, jakarta.servlet.
- Boot 4.0/4.1: Tomcat 11.0.x, Servlet 6.1.

**Đánh giá:** lựa chọn mặc định tốt cho Servlet; dễ vận hành khi ứng dụng phụ thuộc Filter, Servlet listener, HTTP session và thư viện theo Jakarta Servlet. Khi chạy WebFlux trên Tomcat, không tự giả định rằng mã dựa vào Servlet request/session có thể sử dụng như trong MVC.

### 5.2. Eclipse Jetty

**Spring MVC:** Jetty là Servlet container thay thế Tomcat, có Spring Boot starter chính thức ở các dòng đang xét.

**Spring WebFlux:** hỗ trợ thông qua non-blocking Servlet adapter. Jetty còn cung cấp HTTP client riêng, nhưng chọn Jetty làm server **không tự chọn** implementation HTTP client của WebClient.

**Mốc tương thích:**

- Boot 2.7: Jetty 9.4 với Servlet 3.1 hoặc Jetty 10.0 với Servlet 4.0.
- Boot 3.2/3.5: Jetty 12.0 với Servlet 6.0.
- Boot 4.0/4.1: Jetty 12.1.x với Servlet 6.1.

**Đánh giá:** phù hợp khi tổ chức đã dùng Jetty hoặc cần tính năng/đặc tính vận hành riêng của Jetty. Khi nâng cấp Jetty 12, lưu ý các mô-đun, API và môi trường Jakarta EE tương ứng; **Jetty 12.0 và 12.1 không mặc nhiên hoán đổi được giữa Boot 3.5 và 4.x**.

### 5.3. Undertow

**Spring MVC:** Boot 2.7 và các dòng Boot 3.x phù hợp đã cung cấp **spring-boot-starter-undertow**. Undertow vừa là HTTP server vừa có khả năng Servlet container.

**Spring WebFlux:** trong Boot 2.x/3.x, Spring Boot cung cấp cách sử dụng Undertow thay cho Reactor Netty ở tầng HTTP server, với cơ chế tương thích của Spring WebFlux.

**Mốc tương thích:**

- Boot 2.7: Undertow 2.0, Servlet 4.0.
- Boot 3.2/3.5: Undertow 2.3, Servlet 6.0.
- Boot 4.x: không có tích hợp embedded Undertow được hỗ trợ chính thức.

**Đánh giá:** Undertow có thể là lựa chọn hợp lệ trong dự án Boot 3.5. Tuy nhiên, trước khi đưa vào kiến trúc dài hạn, phải xét kế hoạch nâng cấp Boot 4. Spring Boot 4 đã bỏ hỗ trợ Undertow do yêu cầu Servlet 6.1; cố giữ starter cũ từ Boot 3.x không phải cách nâng cấp được hỗ trợ.

### 5.4. Reactor Netty

**Spring MVC:** không phải Servlet container; không dùng làm embedded server cho Spring MVC.

**Spring WebFlux:** là runtime HTTP mặc định của **spring-boot-starter-webflux**. Nó dùng các event loop và API Netty, không cần cầu nối Servlet để xử lý HTTP.

**Phiên bản:** Boot quản lý phiên bản Reactor Netty và Netty theo BOM của chính nhánh Boot, không dùng bảng Servlet ở trên để chọn. Tránh ghi đè độc lập phiên bản Netty nếu chưa kiểm tra tương thích của Reactor, Spring Framework và Boot.

**Đánh giá:** lựa chọn thông dụng cho ứng dụng reactive có HTTP client bất đồng bộ, R2DBC hoặc streaming. Lợi ích non-blocking chỉ đạt được nếu các bước I/O quan trọng không chặn event loop; việc thay Tomcat bằng Reactor Netty không tự chữa được truy vấn JDBC chậm hoặc logic blocking.

## 6. Ví dụ cấu hình dependency trên Spring Boot 3.5

Các ví dụ sau dành cho **Maven + Spring Boot 3.5.x**. Mỗi khối mô tả dependency trong phần dependencies của POM; **không ghép tất cả các cấu hình server vào cùng một ứng dụng**.

### 6.1. MVC + Tomcat mặc định

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Đây là cách đơn giản nhất. Starter web mang theo Tomcat; ứng dụng dùng Spring MVC nếu không thay đổi loại ứng dụng bằng cấu hình đặc biệt.

### 6.2. MVC + Jetty

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
        </exclusion>
    </exclusions>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jetty</artifactId>
</dependency>
~~~

Đã loại Tomcat và thêm Jetty. Để Boot dependency management chọn Jetty 12.0 tương thích, không ép phiên bản thủ công nếu không có lý do đã kiểm thử.

### 6.3. MVC + Undertow (chỉ trên Boot còn hỗ trợ)

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
        </exclusion>
    </exclusions>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-undertow</artifactId>
</dependency>
~~~

Ví dụ hợp lệ trong Boot 3.5. **Không áp dụng khi nâng lên Boot 4.x.**

### 6.4. WebFlux + Reactor Netty mặc định

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Starter WebFlux mặc định đưa Reactor Netty vào classpath. Không cần thêm Tomcat, Jetty hoặc Undertow để chạy một HTTP server reactive cơ bản.

### 6.5. WebFlux + Tomcat

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-reactor-netty</artifactId>
        </exclusion>
    </exclusions>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
</dependency>
~~~

Mục đích là chọn Tomcat làm HTTP server **của WebFlux**. Nếu ứng dụng cũng dùng WebClient với Reactor Netty HTTP client, phải giữ dependency client phù hợp hoặc cấu hình một connector HTTP client khác; việc đổi server không bắt buộc phải đổi client.

**Lưu ý với Boot 4.x:** Spring Boot có cấu trúc starter và module được tổ chức lại (chẳng hạn starter web MVC riêng). Hãy lấy đúng tên starter và ví dụ dependency từ tài liệu Boot 4.x, đồng thời kiểm tra Undertow đã bị loại bỏ. Không sao chép nguyên POM Boot 3.x rồi chỉ đổi thuộc tính version.

## 7. Ví dụ chạy được: kiểm tra Spring MVC với Tomcat

Đây là ứng dụng Java 17 và Maven dùng Boot 3.5.16 để chứng minh một server Servlet chạy thành công. Phiên bản 3.5.16 là một bản vá thuộc nhánh Boot 3.5 được tài liệu tham chiếu; khi làm dự án thực tế nên chọn bản vá được tổ chức phê duyệt và được bảo trì.

### Cấu trúc

~~~text
runtime-check/
├── pom.xml
└── src/main/java/com/example/runtime/
    ├── RuntimeCheckApplication.java
    └── RuntimeController.java
~~~

### File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>runtime-check</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### File RuntimeCheckApplication.java

~~~java
package com.example.runtime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RuntimeCheckApplication {
    public static void main(String[] args) {
        SpringApplication.run(RuntimeCheckApplication.class, args);
    }
}
~~~

### File RuntimeController.java

~~~java
package com.example.runtime;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RuntimeController {
    @GetMapping("/runtime")
    public Result runtime() {
        return new Result("servlet", "ok");
    }

    public record Result(String stack, String status) {}
}
~~~

Khởi chạy với JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Ở terminal khác:

~~~bash
curl -s http://localhost:8080/runtime
~~~

Response body mong đợi:

~~~json
{"stack":"servlet","status":"ok"}
~~~

Ví dụ này chỉ chứng minh endpoint Spring MVC chạy và trả JSON. Để xác nhận **Tomcat chính xác**, xem startup log và dependency tree. Nếu thay dependency sang Jetty theo mục 6.2, giữ nguyên mã Java rồi chạy lại để chứng minh controller vẫn hoạt động trên Servlet container khác.

### Kiểm tra server thực tế trong dependency tree

~~~bash
mvn dependency:tree
~~~

Trong output, tìm các nhóm hiện diện: **org.apache.tomcat.embed** cho Tomcat; **org.eclipse.jetty** cho Jetty; **io.undertow** cho Undertow; **io.projectreactor.netty** cho Reactor Netty. Tên dependency còn sót lại không luôn chứng minh nó là **server được khởi động**: một thư viện có thể chỉ dùng ở phía HTTP client. Cần đối chiếu với startup log và các bean web server thực tế.

### Ví dụ WebFlux tối giản (mã minh họa riêng)

Đoạn controller sau dành cho một **dự án WebFlux riêng có main Spring Boot và starter-webflux**, không thay trực tiếp controller MVC khi còn starter web MVC:

~~~java
package com.example.runtime;

import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReactiveController {
    @GetMapping("/reactive")
    public Mono<String> reactive() {
        return Mono.just("ok");
    }
}
~~~

Với ứng dụng WebFlux đã khởi chạy ở cổng 8080, gọi **GET /reactive** sẽ trả body **ok**. Giá trị Mono cho thấy API trả Publisher, nhưng chưa chứng minh toàn bộ đường xử lý I/O không chặn; cần kiểm tra các dependency được gọi trong pipeline.

## 8. Quy trình đánh giá tương thích từng phiên bản

Lặp lại đúng quy trình sau khi đổi Boot, server hoặc Java:

1. **Khóa phiên bản Boot cụ thể:** ví dụ 3.5.16 hoặc một bản vá 4.1.x. Dùng tài liệu tương ứng với chính bản đó.
2. **Chọn web stack:** Servlet MVC hay WebFlux. Đừng suy từ tên server mà kết luận stack.
3. **Đọc System Requirements:** lấy Java tối thiểu, Servlet baseline và các dòng Tomcat/Jetty/Undertow được hỗ trợ.
4. **Đọc Embedded Web Servers:** xác định starter chính thức và cách loại server mặc định để thay bằng server mới.
5. **Để BOM quản lý dependency:** xác minh các artifact đã resolve qua Maven dependency tree hoặc Gradle dependencies; tránh đưa nhiều server cùng lúc mà không có chủ đích.
6. **Khởi động thật:** kiểm tra log về server thực tế, cổng, servlet/reactive application context, exception và health.
7. **Smoke test HTTP:** gửi GET, POST với JSON và case lỗi; kiểm tra status, content type, body, encoding và routing.
8. **Kiểm thử tương thích nâng cao nếu có:** Filter/Servlet API/session/WebSocket với MVC, hoặc streaming/backpressure/timeout với WebFlux.
9. **Đánh giá vận hành:** cấu hình TLS, proxy, keep-alive, graceful shutdown, metrics, thread hoặc event loop, hiệu năng dưới tải thực tế.
10. **Ghi nhận bằng chứng:** phiên bản Boot, Java, server, Servlet API, dependency tree, startup log và kết quả test để người khác tái lập.

Có thể dùng lệnh dưới đây để xác nhận phiên bản phụ thuộc đã được Maven giải quyết:

~~~bash
mvn dependency:tree
mvn help:effective-pom
~~~

Lệnh này cần chạy tại thư mục dự án Maven có pom.xml hợp lệ và có thể cần truy cập kho dependency lần đầu.

## 9. Các lỗi đánh giá phiên bản thường gặp

| Nhận định hoặc lỗi | Vì sao sai | Cách xử lý |
|---|---|---|
| "Tomcat hỗ trợ reactive nên mọi ứng dụng Tomcat là reactive" | Tomcat có thể chạy cả MVC lẫn WebFlux; stack do framework và dependency quyết định | Kiểm tra starter, ApplicationContext và controller API |
| "Reactor Netty thay thế Tomcat cho Servlet MVC" | Netty không hiện thực Servlet container | Dùng Tomcat/Jetty/Undertow phù hợp hoặc chuyển hẳn sang WebFlux |
| "Mọi Spring Boot 3.x đều dùng cùng Jetty/Servlet" | Ma trận phụ thuộc theo dòng minor và bản vá, đặc biệt giai đoạn đầu Boot 3 | Đọc System Requirements đúng version |
| "Undertow 2.3 chạy được với Boot 3.5 thì Boot 4 cũng hỗ trợ" | Boot 4 nâng baseline Servlet lên 6.1 và bỏ hỗ trợ Undertow | Chọn Tomcat 11 hoặc Jetty 12.1 khi lên Boot 4 |
| "Chỉ đổi Tomcat 9 thành 10/11 là nâng cấp xong" | Đổi từ javax.servlet sang jakarta.servlet và đổi mức Servlet/Jakarta EE | Nâng code, library và Boot đồng bộ |
| "Có Mono/Flux nghĩa là I/O đã non-blocking" | Controller có thể vẫn gọi thư viện blocking | Đo event loop blocking và rà soát JDBC/HTTP client |
| "Thêm webflux starter luôn đổi app MVC thành reactive" | Khi cả MVC và WebFlux cùng tồn tại, Boot thường tự chọn MVC | Xác định rõ stack; dùng starter/loại ứng dụng nhất quán |
| "Thấy Netty trong dependency tree nghĩa là server Netty đang chạy" | Reactor Netty có thể được dùng chỉ làm HTTP client | Xem log khởi động và cấu hình web server |
| "Servlet 6.1 chạy được ở mọi Jetty 12" | Jetty 12.0 và 12.1 có baseline khác nhau trong bảng Boot | Chọn dòng Jetty tương thích với Boot đang dùng |
| "Có thể ép phiên bản server mới nhất độc lập" | Server mới có thể không khớp module auto-configuration hay Jakarta API | Ưu tiên BOM của Boot, chỉ override khi đã kiểm thử |

### Khi chọn WebFlux cần đánh giá gì thêm?

Servlet MVC có thể rất hiệu quả với thread pool và I/O đồng bộ; không nên chọn WebFlux chỉ vì tên gọi "reactive". WebFlux thường phát huy lợi ích khi toàn bộ luồng I/O quan trọng đều không chặn và cần xử lý nhiều tác vụ đồng thời hoặc streaming. Các truy vấn cơ sở dữ liệu, HTTP client, transaction, thư viện SDK và chiến lược timeout phải tương thích với mô hình đó.

Trên Tomcat/Jetty, WebFlux dùng Servlet non-blocking I/O qua adapter; không nên sử dụng trực tiếp Servlet Filter hoặc servlet request/session API như trong ứng dụng MVC để điều khiển pipeline WebFlux.

## 10. Hướng dẫn lựa chọn theo tình huống

**Tình huống A – Ứng dụng CRUD dùng JPA và Spring MVC trên Boot 3.5.** Lựa chọn có chi phí bảo trì thấp là Tomcat 10.1 mặc định. Có thể đổi sang Jetty 12.0 hoặc Undertow 2.3 khi có lý do vận hành và đã kiểm thử tương thích.

**Tình huống B – API streaming WebFlux trên Boot 3.5.** Dùng Reactor Netty mặc định trước, sau đó đo latency, throughput, event loop và hiệu năng của các dependency. Chỉ đổi Tomcat/Jetty nếu cần tiêu chuẩn hạ tầng hoặc có kết quả đo hỗ trợ.

**Tình huống C – Nâng ứng dụng Undertow từ Boot 3.5 lên Boot 4.** Đây là thay đổi kiến trúc server: loại Undertow starter, chọn Tomcat 11 hoặc Jetty 12.1, cập nhật Servlet 6.1/Jakarta EE 11 và chạy lại test thực tế.

**Tình huống D – Ứng dụng Boot 2.7 cũ dùng Servlet Filter theo javax.** Không chỉ thay server sang Tomcat 10.1: cần nâng Boot và thư viện liên quan, chuyển mã sang Jakarta namespace, kiểm thử Filter, listener và Servlet API. Boot 2.7 và Boot 3/4 không có cùng baseline.

## 11. Checklist chốt khả năng hỗ trợ

- [ ] Biết **chính xác** phiên bản Spring Boot, Java và server nhúng.
- [ ] Xác định Spring MVC/Servlet hay Spring WebFlux/reactive.
- [ ] So khớp bảng Servlet API với máy chủ và namespace javax/jakarta.
- [ ] Chọn server còn được Boot hỗ trợ **trong đúng phiên bản**.
- [ ] Dùng starter chính thức; loại starter máy chủ mặc định khi thay.
- [ ] Không nhầm thư viện HTTP client với HTTP server đang chạy.
- [ ] Dùng dependency management, kiểm tra phiên bản được resolve.
- [ ] Khởi động, kiểm tra log, smoke test endpoint và đánh giá vận hành.
- [ ] Ghi lại compatibility matrix và bằng chứng cho lần nâng cấp sau.

## 12. Tài liệu tham khảo chính thức

1. Spring Boot 2.7.18 Reference – System Requirements: https://docs.spring.io/spring-boot/docs/2.7.x/reference/htmlsingle/
2. Spring Boot 3.2.12 Reference – System Requirements: https://docs.spring.io/spring-boot/docs/3.2.12/reference/htmlsingle/
3. Spring Boot 3.5 – System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
4. Spring Boot 3.5 – Embedded Web Servers: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
5. Spring Boot 4.0 – System Requirements: https://docs.spring.io/spring-boot/4.0/system-requirements.html
6. Spring Boot 4.x – Embedded Web Servers: https://docs.spring.io/spring-boot/4.0/how-to/webserver.html
7. Spring Boot 4.0 Migration Guide – Undertow removal: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide
8. Spring Framework – WebFlux overview and supported servers: https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html

**Kết luận:** khả năng hỗ trợ Servlet hoặc reactive là quan hệ giữa **web stack, máy chủ, phiên bản Boot và mức API yêu cầu**. Tomcat/Jetty hỗ trợ cả MVC lẫn WebFlux với cách tích hợp phù hợp; Reactor Netty dành cho WebFlux; Undertow phù hợp trong các dòng Boot 2.x/3.x được hỗ trợ nhưng đã bị loại bỏ ở Boot 4.x. Luôn xác nhận trên đúng version, dependency tree và ứng dụng chạy thực tế.
