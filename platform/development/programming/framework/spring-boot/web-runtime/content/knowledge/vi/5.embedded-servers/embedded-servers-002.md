# Máy chủ mặc định của từng starter và kiểm tra cây phụ thuộc

Trong Spring Boot, câu hỏi “ứng dụng đang dùng máy chủ web nào?” cần phân biệt ba điều: **starter khai báo**, **dependency thực sự được Gradle/Maven resolve** và **server được Spring Boot khởi tạo lúc chạy**. Với cấu hình Spring Boot 3.3.x thông thường, `spring-boot-starter-web` dẫn tới **Tomcat nhúng**, còn `spring-boot-starter-webflux` dẫn tới **Reactor Netty**. Tuy nhiên, dependency có thể bị exclude, thay thế, được kéo gián tiếp từ starter khác hoặc chỉ được dùng ở vai trò HTTP client. Do đó không nên đoán server thực tế chỉ từ một dòng trong `build.gradle`.

Bài học này thuộc nhóm **Máy chủ nhúng**: tập trung vào starter, máy chủ mặc định, lý do dependency xuất hiện, cách xem cây phụ thuộc và cách xác nhận runtime. Ví dụ dùng Spring Boot 3.3.x, Java 21 và Gradle; với Spring Boot ở major version khác, hãy kiểm tra tài liệu và dependency graph tương ứng với phiên bản đang dùng.

## 1. Starter, stack, server và classpath khác nhau thế nào?

| Khái niệm | Bản chất | Ví dụ |
| --- | --- | --- |
| **Starter** | Dependency tập hợp những thư viện thường cần cho một khả năng | `spring-boot-starter-web` |
| **Web stack** | Mô hình framework xử lý HTTP request | Spring MVC/Servlet hoặc Spring WebFlux |
| **Web server** | Thành phần mở socket, tiếp nhận kết nối và trao đổi HTTP | Tomcat, Jetty, Undertow, Reactor Netty |
| **Servlet container** | Runtime thực thi Jakarta Servlet API (Servlet, Filter, Listener...) | Tomcat, Jetty, Undertow |
| **Classpath** | Danh sách class/JAR có hiệu lực tại compile hoặc runtime | `runtimeClasspath` |
| **Auto-configuration** | Spring Boot tạo bean phù hợp với điều kiện classpath, properties và bean có sẵn | `ServletWebServerFactoryAutoConfiguration` |
| **Running server** | Server thực sự được context khởi tạo và lắng nghe HTTP | `TomcatWebServer` hoặc `NettyWebServer` |

Một starter có thể đưa server vào classpath **theo quan hệ phụ thuộc bắc cầu (transitive dependency)**. Nhưng Spring Boot chỉ tạo một web server phù hợp với application type và cấu hình runtime. Sự xuất hiện của một JAR không đồng nghĩa rằng JAR đó được chọn làm server.

Ví dụ, một ứng dụng Spring MVC dùng thêm `spring-boot-starter-webflux` để gọi dịch vụ ngoài bằng `WebClient` có thể chứa cả thư viện Tomcat và Reactor Netty trong cây phụ thuộc, nhưng server được chọn mặc định vẫn là Tomcat của MVC. Reactor Netty có thể được dùng làm HTTP client.

## 2. Bảng máy chủ mặc định của các starter quan trọng

Bảng dưới mô tả **cấu hình thông thường của Spring Boot 3.3.x**, khi không có exclusion, replacement hoặc bean factory tùy chỉnh:

| Starter hoặc nhóm dependency | Web stack / mục đích | Server mặc định hoặc ý nghĩa |
| --- | --- | --- |
| `spring-boot-starter-web` | Spring MVC trên Servlet | **Tomcat** qua `spring-boot-starter-tomcat` |
| `spring-boot-starter-webflux` | Reactive WebFlux | **Reactor Netty** qua `spring-boot-starter-reactor-netty` |
| `spring-boot-starter-jersey` | JAX-RS/Jersey trên Servlet | **Tomcat** trong dependency mặc định của starter 3.3.x |
| `spring-boot-starter-tomcat` | Starter cho Servlet container Tomcat | Cung cấp Tomcat; bản thân starter chưa quyết định ứng dụng có chạy web hay không |
| `spring-boot-starter-jetty` | Starter thay thế/khai báo server Jetty | Cung cấp Jetty; cần stack và cấu hình thích hợp |
| `spring-boot-starter-undertow` | Starter thay thế/khai báo server Undertow trong Boot 3.3.x | Cung cấp Undertow; cần stack và cấu hình thích hợp |
| `spring-boot-starter-reactor-netty` | HTTP runtime của Reactor Netty | Có thể phục vụ WebFlux hoặc được dùng với HTTP client; không mặc định biến Spring MVC thành WebFlux |
| `spring-boot-starter-data-jpa`, `spring-boot-starter-security`, `spring-boot-starter-validation`, `spring-boot-starter-actuator` | Database, bảo mật, validation, monitoring | **Không tự xác định máy chủ web mặc định** chỉ vì được khai báo |

Các starter chuyên biệt như WebSocket, Spring Web Services, Spring Data REST hoặc những starter của bên thứ ba cần được kiểm tra trên **cây phụ thuộc thực tế**. Chúng có thể bổ sung web libraries hoặc mang theo một web starter qua đường phụ thuộc khác; không nên đồng nhất tên “starter” với việc có một server nhúng riêng.

Hai lựa chọn được tài liệu Spring Boot nêu trực tiếp:

- **Servlet:** `spring-boot-starter-web → spring-boot-starter-tomcat → Tomcat`.
- **Reactive:** `spring-boot-starter-webflux → spring-boot-starter-reactor-netty → Reactor Netty`.

Tomcat, Jetty và Undertow cung cấp môi trường Servlet; Reactor Netty là HTTP server/reactive runtime, không phải Servlet container để chạy `DispatcherServlet` của Spring MVC.

## 3. Vì sao starter-web chọn Tomcat?

Khi khai báo:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Gradle resolve các dependency do starter yêu cầu. Một phần cây tiêu biểu (đã rút gọn và bỏ số phiên bản vì phụ thuộc Boot BOM) là:

~~~text
runtimeClasspath
\--- org.springframework.boot:spring-boot-starter-web
     +--- org.springframework.boot:spring-boot-starter
     +--- org.springframework.boot:spring-boot-starter-json
     +--- org.springframework:spring-web
     +--- org.springframework:spring-webmvc
     \--- org.springframework.boot:spring-boot-starter-tomcat
          +--- org.apache.tomcat.embed:tomcat-embed-core
          +--- org.apache.tomcat.embed:tomcat-embed-el
          \--- org.apache.tomcat.embed:tomcat-embed-websocket
~~~

Đây là cây **minh họa**, không phải output nguyên văn của một lần chạy Gradle cụ thể. Tùy phiên bản, report sẽ có thêm constraints, version, ký hiệu rút gọn và những nhánh dependency khác.

Vai trò từng nhóm:

- `spring-webmvc` cung cấp `DispatcherServlet`, handler mapping và xử lý HTTP theo Spring MVC.
- `spring-boot-starter-tomcat` cung cấp server/container tích hợp.
- `tomcat-embed-core` chứa phần lõi Tomcat nhúng.
- `spring-boot-starter-json` đưa những thư viện JSON phù hợp vào ứng dụng.

Khi Spring Boot phát hiện ứng dụng Servlet, auto-configuration tạo một `ServletWebServerFactory` thích hợp (mặc định thường là `TomcatServletWebServerFactory`), rồi dùng factory đó khởi động server. Controller và service là bean Spring, còn Tomcat chịu trách nhiệm nhận request và chạy Servlet/Filter.

**Dấu hiệu cần tìm trên dependency graph:** `spring-boot-starter-tomcat` và `org.apache.tomcat.embed:tomcat-embed-core`. Nhưng xác nhận lần cuối phải là runtime web server, vì dependency vẫn có thể hiện diện mà không được chọn hoặc ứng dụng có thể chạy theo cách triển khai khác.

## 4. Vì sao starter-webflux chọn Reactor Netty?

Với:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Một nhánh quan trọng trong cây là:

~~~text
runtimeClasspath
\--- org.springframework.boot:spring-boot-starter-webflux
     +--- org.springframework:spring-webflux
     +--- org.springframework.boot:spring-boot-starter-json
     \--- org.springframework.boot:spring-boot-starter-reactor-netty
          \--- io.projectreactor.netty:reactor-netty-http
~~~

Reactor Netty cung cấp HTTP server phù hợp với cách xử lý reactive và non-blocking của WebFlux. Spring Boot thường tạo `ReactiveWebServerApplicationContext` và `NettyReactiveWebServerFactory` (với Netty được chọn).

Cần phân biệt:

- `spring-webflux` là web framework.
- Reactor là nền tảng Reactive Streams sử dụng trong hệ sinh thái Spring.
- `reactor-netty-http` là thư viện triển khai HTTP client/server dựa trên Netty.
- `NettyWebServer` là wrapper server mà Spring Boot dùng ở runtime.

WebFlux cũng có thể được triển khai trên những server khác được phiên bản Boot tương ứng hỗ trợ. Không đồng nhất “WebFlux” với “bắt buộc Netty”, cũng như không đồng nhất “Spring MVC” với “bắt buộc Tomcat”.

## 5. Nhiều starter web cùng có mặt: sự khác biệt giữa “có dependency” và “chạy server”

Giả sử dự án khai báo cả hai:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Khi cả Spring MVC và WebFlux cùng có trên classpath, Spring Boot 3.3 thông thường **ưu tiên Servlet/MVC** khi tự xác định `WebApplicationType`. Hệ quả thường gặp:

- Ứng dụng khởi động bằng một `ServletWebServerApplicationContext`.
- Embedded Tomcat vẫn là server mặc định từ starter-web.
- Những API reactive như `WebClient` có thể được sử dụng để gọi dịch vụ bên ngoài.
- Sự có mặt của `spring-boot-starter-reactor-netty` trong graph **không chứng minh rằng Reactor Netty đang lắng nghe HTTP request từ client**.

Bảng phân tích:

| Dependency hiện diện | App type mặc định (nếu không override) | Server thường được khởi động |
| --- | --- | --- |
| Chỉ starter-web | SERVLET | Tomcat |
| Chỉ starter-webflux | REACTIVE | Reactor Netty |
| Cả starter-web và starter-webflux | SERVLET | Tomcat |
| Chỉ các starter không liên quan web | NONE (nếu không có web framework khác) | Không có web server nhúng |
| Starter-web nhưng thay Tomcat bằng Jetty đúng cách | SERVLET | Jetty |

Có thể cấu hình `spring.main.web-application-type` hoặc gọi `SpringApplication.setWebApplicationType(...)` để chọn loại ứng dụng khi cần, nhưng **không** nên ép REACTIVE chỉ để thấy Netty chạy: controller, Servlet filters, Spring Security và các dependency liên quan phải tương thích với stack được chọn.

## 6. Vì sao kiểm tra runtimeClasspath trước?

Gradle quản lý nhiều configuration khác nhau:

- `implementation`: dependency dùng để compile và chạy ứng dụng.
- `compileClasspath`: tập class/JAR dùng cho quá trình biên dịch.
- `runtimeClasspath`: tập dependency được resolve để ứng dụng chạy (bao gồm dependency runtime phù hợp).
- `testRuntimeClasspath`: dependency dùng khi chạy kiểm thử; có thể chứa test server hoặc thư viện khác.
- `annotationProcessor`: classpath dành cho annotation processor, không phải server runtime.

Muốn tìm server thực tế được mang theo để chạy ứng dụng, **runtimeClasspath** thường là điểm bắt đầu phù hợp hơn compileClasspath và testRuntimeClasspath. Với WAR triển khai vào external container hoặc ứng dụng có custom packaging, còn phải xem scope cung cấp bởi container và artifact được triển khai.

Chạy tại thư mục project có Gradle wrapper:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Trong Windows PowerShell:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
~~~

Với multi-project Gradle, chỉ định đúng subproject:

~~~bash
./gradlew :my-web-app:dependencies --configuration runtimeClasspath
~~~

Thay `:my-web-app` bằng path Gradle thật của module chứa ứng dụng. Không giả định cây dependency của root project là cây của mọi module con.

**Cách đọc report:** một dòng ở đầu nhánh là dependency trực tiếp hoặc cha; các dòng thụt lề tiếp theo biểu diễn những dependency đi qua nó. Hãy truy ngược nhánh từ `spring-boot-starter-tomcat` về starter hoặc thư viện đã kéo nó vào.

## 7. dependencyInsight: tìm chính xác ai đã kéo server vào

Lệnh `dependencies` cho thấy toàn cảnh; `dependencyInsight` trả lời “dependency này từ đâu đến và tại sao phiên bản này được chọn?”.

Ví dụ với Tomcat:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-boot-starter-tomcat \
  --configuration runtimeClasspath
~~~

Với thư viện lõi Tomcat:

~~~bash
./gradlew dependencyInsight \
  --dependency tomcat-embed-core \
  --configuration runtimeClasspath
~~~

Với Reactor Netty:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-boot-starter-reactor-netty \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency reactor-netty-http \
  --configuration runtimeClasspath
~~~

Các lệnh Bash có dấu gạch chéo ngược để nối dòng. Trên PowerShell, nên viết nguyên một dòng:

~~~powershell
.\gradlew.bat dependencyInsight --dependency spring-boot-starter-tomcat --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency reactor-netty-http --configuration runtimeClasspath
~~~

Với subproject:

~~~bash
./gradlew :my-web-app:dependencyInsight \
  --dependency spring-boot-starter-tomcat \
  --configuration runtimeClasspath
~~~

`dependencyInsight` giúp phát hiện:

1. Dependency được khai báo trực tiếp hay kéo qua starter.
2. Có nhiều đường phụ thuộc tới cùng một module hay không.
3. Version được chọn có bị nâng/hạ do dependency constraints hoặc conflict resolution không.
4. Dependency bạn định exclude còn được một nhánh khác đưa vào không.
5. Khi đổi Tomcat sang Jetty, Tomcat còn trên runtimeClasspath qua dependency khác không.

Để tránh nhận nhầm kết quả, nên tìm bằng `group:name` đầy đủ khi có nhiều module tên tương tự, ví dụ `org.springframework.boot:spring-boot-starter-tomcat`.

### 7.1. Ký hiệu thường xuất hiện trong cây Gradle

| Ký hiệu trong output | Ý nghĩa |
| --- | --- |
| `+---` hoặc `\---` | Một nhánh dependency |
| `(*)` | Nhánh dependency này đã được hiển thị ở vị trí khác; Gradle rút gọn phần lặp |
| `(c)` | Dependency constraint, **không** nhất thiết là artifact thực sự được đưa vào classpath |
| `a:1.0 -> 2.0` | Version yêu cầu và version được chọn sau resolution khác nhau |
| `(n)` hoặc thông báo unresolved | Dependency không resolve được trong report tương ứng |
| `FAILED` | Lỗi resolution cần kiểm tra cụ thể |

Ví dụ minh họa:

~~~text
+--- org.springframework.boot:spring-boot-starter-web
|    \--- org.springframework.boot:spring-boot-starter-tomcat
|         \--- org.apache.tomcat.embed:tomcat-embed-core
\--- some-other-library
     \--- org.apache.tomcat.embed:tomcat-embed-core (*)
~~~

Nhánh thứ hai có `(*)` vẫn cho thấy dependency được dùng qua một đường khác. Không xem `(*)` là lỗi, cũng đừng coi `(c)` là bằng chứng một server có mặt thực sự.

### 7.2. Nếu report cho “No dependencies matching…”

Kết quả đó có thể nghĩa là module cần tìm không tồn tại trong configuration cụ thể, hoặc tên tìm kiếm không khớp. Kiểm tra theo thứ tự:

1. Chạy trên đúng Gradle subproject chưa?
2. Đã chọn `runtimeClasspath` của ứng dụng thay vì configuration test?
3. Tên module tìm kiếm có đúng không?
4. Có exclude dependency, thay thế module hay thay đổi starter không?
5. Có đang xem build variant, artifact hoặc ứng dụng đóng gói khác với thứ thực sự chạy không?

Không tự động kết luận ứng dụng đang dùng Jetty chỉ vì không tìm thấy Tomcat. Phải xác định server nào thực sự được chọn.

## 8. Từ dependency graph đến xác nhận runtime

Dependency graph trả lời **có thể có những implementation nào**. Runtime phải trả lời **implementation nào đã được chọn**.

Với Spring Boot 3.3, một số lớp giúp nhận diện:

| Loại ứng dụng | ApplicationContext điển hình | Factory thường có | WebServer runtime |
| --- | --- | --- | --- |
| Servlet + Tomcat | `ServletWebServerApplicationContext` | `TomcatServletWebServerFactory` | `TomcatWebServer` |
| Servlet + Jetty | `ServletWebServerApplicationContext` | `JettyServletWebServerFactory` | `JettyWebServer` |
| Servlet + Undertow | `ServletWebServerApplicationContext` | `UndertowServletWebServerFactory` | `UndertowWebServer` |
| Reactive + Reactor Netty | `ReactiveWebServerApplicationContext` | `NettyReactiveWebServerFactory` | `NettyWebServer` |

Các tên trên là implementation classes thuộc phiên bản Boot 3.x. Chúng có giá trị chẩn đoán, nhưng nghiệp vụ không nên phụ thuộc vào chúng nếu không có yêu cầu cụ thể.

Khi chạy, có thể kiểm tra log khởi động server (Tomcat/Netty/Jetty), địa chỉ và cổng thật, process/JVM và ApplicationContext. Log tự động có thể thay đổi tùy mức log hoặc cấu hình startup, vì vậy một đoạn kiểm tra `WebServer` trực tiếp sẽ đáng tin hơn nếu cần chứng cứ trong chương trình.

## 9. Ví dụ hoàn chỉnh: ứng dụng Servlet và xác định Tomcat thật

Ví dụ tạo một ứng dụng Spring Boot 3.3.x, Java 21, Gradle. Nó in implementation WebServer được Spring Boot khởi động và cung cấp một endpoint HTTP để kiểm chứng.

Cấu trúc:

~~~text
server-selection-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/serverselection/
    ├── ServerSelectionApplication.java
    └── HelloController.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'server-selection-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

**src/main/java/com/example/serverselection/ServerSelectionApplication.java**

~~~java
package com.example.serverselection;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.server.WebServer;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class ServerSelectionApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
            SpringApplication.run(ServerSelectionApplication.class, args);

        if (context instanceof ServletWebServerApplicationContext servlet) {
            WebServer server = servlet.getWebServer();
            System.out.println("STACK=SERVLET");
            System.out.println("SERVER=" + server.getClass().getSimpleName());
            System.out.println("PORT=" + server.getPort());
        } else {
            System.out.println("STACK=OTHER");
        }
    }
}
~~~

**src/main/java/com/example/serverselection/HelloController.java**

~~~java
package com.example.serverselection;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public Map<String, String> hello() {
        return Map.of("message", "Hello from Spring MVC");
    }
}
~~~

Lưu ý để chạy: project cần có Gradle wrapper tương thích và JDK 21; với Gradle đã cài, có thể tạo wrapper, sau đó chạy:

~~~bash
gradle wrapper --gradle-version 8.5
./gradlew bootRun
~~~

Nếu dự án đã có wrapper, chỉ cần `./gradlew bootRun`. Trên Windows PowerShell dùng `.\gradlew.bat bootRun`.

Trong cấu hình mặc định không có override port/server, sau các log khởi động dự kiến sẽ xuất hiện:

~~~text
STACK=SERVLET
SERVER=TomcatWebServer
PORT=8080
~~~

Đây là ba dòng do code mẫu in ra, **không phải toàn bộ stdout của Spring Boot**. Nếu cấu hình `server.port` khác hoặc dùng `server.port=0`, giá trị PORT sẽ phản ánh cổng thực tế. Nếu thay Tomcat bằng Jetty phù hợp, tên SERVER thay đổi tương ứng.

Kiểm thử HTTP bằng terminal khác:

~~~bash
curl -i http://localhost:8080/hello
~~~

Kết quả dự kiến có status `200 OK` và response JSON:

~~~json
{"message":"Hello from Spring MVC"}
~~~

Kiểm tra dependency của project mẫu:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-boot-starter-tomcat --configuration runtimeClasspath
./gradlew dependencyInsight --dependency tomcat-embed-core --configuration runtimeClasspath
~~~

So sánh ba nguồn chứng cứ: build.gradle khai báo starter-web; dependency graph chứa Tomcat; runtime in `TomcatWebServer`. Khi cả ba khớp, kết luận server đã được thiết lập vững hơn là chỉ nhìn starter name.

## 10. Đổi Tomcat sang Jetty trong Servlet stack

Nếu ứng dụng Spring MVC cần dùng Jetty, phải **loại Tomcat mặc định và thêm Jetty phù hợp**, thay thế dependency starter-web hiện có bằng cấu hình sau:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }

    implementation 'org.springframework.boot:spring-boot-starter-jetty'
}
~~~

Điểm cần nhớ:

1. Đây là phiên bản thay thế cho khối dependency web trước đó, không thêm một starter-web thứ hai.
2. Việc exclude áp dụng theo nhánh dependency. Nếu library khác vẫn kéo Tomcat vào, cần truy nguồn bằng `dependencyInsight` rồi xử lý ở nơi phù hợp.
3. Jetty phải tương thích với Spring Boot và phiên bản Jakarta Servlet đang dùng; tránh tự ép version thủ công khi không cần.
4. Sau khi sửa, chạy lại dependency report và ứng dụng để xác nhận `JettyWebServer`.

Lệnh kiểm tra:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-boot-starter-tomcat \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-boot-starter-jetty \
  --configuration runtimeClasspath
~~~

Nếu đã thay Jetty đúng và không còn nhánh khác kéo Tomcat, graph không nên còn starter-tomcat trong runtimeClasspath. Quan sát runtime mới là bước xác nhận cuối.

Tương tự, trong phạm vi Spring Boot 3.3.x có thể thay bằng `spring-boot-starter-undertow` khi tương thích với project. Không tự giả định những lựa chọn server và tên starter trong major version tương lai sẽ giống 3.3.x.

## 11. Đổi Reactor Netty sang server HTTP khác cho WebFlux

Spring WebFlux hỗ trợ nhiều HTTP runtime trong phạm vi phiên bản Boot tương ứng; `spring-boot-starter-webflux` mặc định kéo Reactor Netty. Khi chuyển sang server khác, phải đánh giá cả dependency và cách WebFlux được triển khai trên server đó.

Ví dụ hướng tiếp cận với Jetty:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-webflux') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-reactor-netty'
    }

    implementation 'org.springframework.boot:spring-boot-starter-jetty'
}
~~~

Đoạn này chỉ minh họa cấu trúc dependency cho Boot 3.3.x. Hãy kiểm tra tài liệu đúng phiên bản, compatibility và tích hợp WebFlux/runtime trước khi dùng trong một ứng dụng thật.

Đặc biệt, đừng exclude Reactor Netty chỉ vì thấy nó trong graph khi ứng dụng dùng `WebClient`: Reactor Netty có thể là HTTP client connector đang được sử dụng. Nếu muốn tách client connector và server runtime, phải cấu hình cả hai phía rõ ràng và kiểm thử request outbound/inbound.

## 12. Một số tình huống khó nhận diện từ cây dependency

### 12.1. Một dependency có nhiều đường đưa vào

`dependencyInsight` có thể hiển thị Tomcat được kéo qua một web starter và thêm một thư viện nội bộ. Exclude ở một nhánh chưa chắc loại được mọi nhánh. Không dùng exclusion toàn cục nếu chưa hiểu lý do nó được yêu cầu.

### 12.2. Có cả Tomcat và Reactor Netty

Đây không luôn là lỗi. Ứng dụng Spring MVC dùng WebClient có thể dùng Tomcat cho server và Reactor Netty cho client. Dùng runtime context để xác nhận, đừng suy luận rằng hai HTTP server cùng mở port chỉ vì cùng xuất hiện trong graph.

### 12.3. Có server JAR nhưng không mở HTTP port

Ứng dụng có thể đặt `spring.main.web-application-type=none`, bị lỗi startup, chạy với external servlet container hoặc khai báo WebServerFactory khác. Việc JAR có trong runtimeClasspath không chứng minh một cổng HTTP đang lắng nghe.

### 12.4. Tìm thấy Tomcat trong testRuntimeClasspath

Dependency kiểm thử có thể mang thêm các thư viện không có trong runtime ứng dụng production. Hãy xem `runtimeClasspath` và artifact cuối cùng thay vì chỉ nhìn test classpath.

### 12.5. Dùng WAR triển khai vào server bên ngoài

Với external Tomcat/Jetty, môi trường triển khai quản lý server và lifecycle. Phân tích thêm `providedRuntime`, WAR packaging, `WEB-INF/lib` và container đang vận hành. Không áp dụng nguyên xi giả định của executable JAR.

### 12.6. Parent/BOM đổi phiên bản nhưng starter giống nhau

Dependency management có thể chọn phiên bản Tomcat hoặc Reactor Netty khác mà không đổi tên starter. `dependencyInsight` cho thấy selected version và nguyên nhân selection, giúp phát hiện conflict hoặc version override không mong muốn. Tránh tự gắn version rời rạc cho các artifact server khi Boot BOM có thể quản lý đồng bộ.

### 12.7. Chạy Gradle report ở sai subproject

Trong multi-project, `./gradlew dependencies` ở root trả dependency của root project, có thể không phải của module khởi chạy. Chọn đúng path `:module:dependencies` rồi kiểm tra cấu hình runtimeClasspath của module ấy.

### 12.8. Nhầm port và loại server

Cả Tomcat và Reactor Netty có thể dùng port mặc định 8080. Chỉ thấy cổng 8080 đang mở **không chứng minh** dùng Tomcat. Kiểm tra log, factory và WebServer implementation.

## 13. Maven có cách kiểm tra tương đương

Với project Maven, dùng `mvn dependency:tree` để xem cây phụ thuộc:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-tomcat
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-reactor-netty
mvn dependency:tree -Dincludes=org.apache.tomcat.embed:tomcat-embed-core
~~~

Các tùy chọn filter phụ thuộc phiên bản maven-dependency-plugin; khi lọc không ra kết quả, xem cây đầy đủ và xác nhận dependency đang được resolve.

Maven `dependency:tree` và Gradle `dependencies` cùng giải quyết câu hỏi “JAR nào có mặt và đi qua đường dependency nào?”. Gradle `dependencyInsight` giúp đào sâu selected version và đường dẫn resolution trên configuration được chỉ định. Hai công cụ **không thay thế** việc xác nhận web server thực sự đang chạy.

## 14. Checklist xác minh server cho một ứng dụng

Khi chuẩn bị triển khai hoặc thay embedded server, kiểm tra theo thứ tự:

1. **Đọc dependency trực tiếp:** ứng dụng khai báo starter-web, starter-webflux, starter-jersey hay chỉ starter không liên quan web?
2. **Chọn đúng module:** với Gradle multi-project, chỉ định project path của ứng dụng cần chạy.
3. **Xem resolved runtimeClasspath:** có starter-tomcat, starter-reactor-netty, starter-jetty hoặc starter-undertow nào?
4. **Truy nguyên bằng dependencyInsight:** dependency server do starter nào hoặc thư viện nào kéo tới? Có nhiều đường không?
5. **Kiểm tra application type:** SERVLET, REACTIVE hay NONE; nếu có cả MVC và WebFlux, đã xác nhận Boot chọn stack nào?
6. **Kiểm tra override:** exclusions, dependency substitutions, version constraints, custom WebServerFactory, cấu hình WAR hoặc external container.
7. **Xem log và runtime WebServer:** implementation được khởi tạo, cổng đang lắng nghe, bind address và trạng thái startup.
8. **Gửi HTTP request thật:** xác nhận ứng dụng có thể nhận request và trả response; kiểm tra port/context path.
9. **Kiểm thử lại sau khi thay server:** Servlet Filter, WebSocket nếu sử dụng, HTTPS/TLS, session, timeout, header, upload và monitoring có hoạt động như yêu cầu?
10. **Giữ dependency nhất quán:** ưu tiên version do Spring Boot BOM quản lý và tài liệu cho phiên bản thực tế.

Có thể nhớ phương pháp theo ba lớp:

~~~text
Dependency khai báo (build.gradle / pom.xml)
               |
               v
Dependency resolve thực tế (runtimeClasspath / dependency:tree)
               |
               v
ApplicationContext + WebServer đã khởi động
               |
               v
HTTP request thực tế, logs và metrics
~~~

**Kết luận:** `spring-boot-starter-web` thông thường kéo Tomcat và khởi động Spring MVC trên Servlet, còn `spring-boot-starter-webflux` kéo Reactor Netty cho WebFlux. Những starter khác không nhất thiết tự mang server, và việc một server library có trong cây chưa đủ để biết nó đang lắng nghe HTTP. Hãy dùng `dependencies` để xem toàn cảnh, `dependencyInsight` để truy nguồn và version, sau đó xác nhận `WebServer` cùng request thực tế trước khi kết luận hoặc thay đổi máy chủ nhúng.

## Tài liệu tham khảo

- Spring Boot 3.3 — Embedded Web Servers: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3 — Servlet Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Gradle — Viewing and Debugging Dependencies: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
