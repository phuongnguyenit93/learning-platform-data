# Triển khai Java SE và ứng dụng Java web

Trong Microsoft Azure, một ứng dụng Java có thể chạy trên máy ảo tự quản lý, trong container hoặc trên dịch vụ nền tảng được quản lý. Khi xây dựng API, trang web hoặc backend Java, **Azure App Service** là lựa chọn Platform as a Service (PaaS) cho phép tập trung vào mã nguồn và vận hành ứng dụng thay vì tự dựng và bảo trì toàn bộ hệ điều hành cùng web server.

Tuy nhiên, “triển khai Java” không chỉ là tải một file lên cloud. Bạn phải quyết định **mô hình chạy**, **định dạng artifact**, **Java runtime**, **web container**, **App Service Plan**, cấu hình ứng dụng, đường mạng, danh tính, logging, scaling và phương án release/rollback.

Bài học này thuộc chương **Ứng dụng web với App Service** của module **CLOUD_PROVIDERS_AZURE**. Trong lộ trình tìm hiểu subscription, resource group, Microsoft Entra ID, mạng ảo, compute, lưu trữ và dữ liệu, chúng ta sẽ triển khai hai kiểu ứng dụng phổ biến:

- **Java SE trên App Service:** một ứng dụng Java có web server nhúng, đóng gói thành **executable JAR**. Ví dụ điển hình là REST API Spring Boot dùng embedded Tomcat/Jetty.
- **Java web trên App Service:** ứng dụng Servlet/Jakarta Servlet đóng gói thành **WAR**, chạy trong **Tomcat** do nền tảng cung cấp. Các stack khác như JBoss EAP có yêu cầu runtime, packaging, licensing và SKU riêng.

> **Điểm cần nhớ:** Java SE trên App Service **không có nghĩa** chạy một chương trình console bất kỳ rồi tự thoát. App Service được thiết kế cho ứng dụng web hoặc dịch vụ HTTP luôn lắng nghe cổng phù hợp, có thể start, restart và scale theo yêu cầu.

## 1. Mục tiêu học tập

Sau khi hoàn thành bài học, bạn có thể:

1. Phân biệt Java SE executable JAR với Java web WAR/Tomcat trong Azure App Service.
2. Giải thích quan hệ giữa **Web App**, **App Service Plan**, **runtime stack**, hệ điều hành và region.
3. Xác định cách chọn phiên bản JDK/Tomcat tương thích với mã nguồn và artifact.
4. Build và kiểm tra một ứng dụng Java SE JAR và một ứng dụng Servlet WAR đơn giản.
5. Tạo App Service Plan/Web App bằng Azure Portal và Azure CLI, triển khai artifact theo đúng loại.
6. Cấu hình biến môi trường, startup, port, health endpoint, logging và secrets một cách an toàn.
7. Kiểm thử ứng dụng qua HTTPS, phân tích lỗi 404/502/503, startup và version mismatch.
8. Thiết kế quy trình CI/CD, staging slot/rollback khi gói dịch vụ hỗ trợ.
9. Hiểu scaling, chi phí, vùng triển khai, mạng riêng và bảo vệ dữ liệu khi ứng dụng chạy production.

## 2. Azure App Service giải quyết bài toán nào?

App Service cung cấp một môi trường hosting ứng dụng web được Azure quản lý. Bạn triển khai code hoặc artifact; nền tảng hỗ trợ quản lý web app, cấu hình runtime, endpoint HTTPS, deployment, logs và các khả năng scale/availability theo **App Service Plan** đã chọn.

Ví dụ một kiến trúc Orders API:

~~~mermaid
flowchart LR
    U["Người dùng / Frontend"] -->|"HTTPS"| A["Azure App Service<br/>Java Orders API"]
    A -->|"Managed identity"| K["Azure Key Vault"]
    A -->|"Kết nối ứng dụng"| D["Azure SQL Database"]
    A -->|"SDK / HTTP"| S["Azure Storage"]
    P["Azure Monitor / App Insights"] -. "Logs, traces, metrics" .-> A
    C["CI/CD pipeline"] -->|"Deploy JAR hoặc WAR"| A
~~~

Bạn không phải tự tạo VM cho mỗi web app. Tuy vậy, **vẫn phải chịu trách nhiệm** về lỗ hổng dependency, logic ứng dụng, cấu hình quyền, dữ liệu, network access, health checks, hiệu năng và chi phí.

### 2.1. Những thành phần Azure cần hiểu

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| **Subscription** | Phạm vi quản lý/billing | Subscription cho môi trường development |
| **Resource group** | Nhóm các tài nguyên có vòng đời/quyền quản trị liên quan | rg-java-app-lab |
| **App Service Plan** | Tập hợp năng lực compute và đặc tính scale/SKU phục vụ một hoặc nhiều Web App | asp-java-linux-lab |
| **Web App** | Tài nguyên cấu hình endpoint, runtime, code deployment và app settings | orders-api-lab |
| **Runtime stack** | Phiên bản Java SE, Tomcat hoặc môi trường Java được App Service hỗ trợ | Java SE với JDK tương thích |
| **Deployment artifact** | File được build để triển khai | orders-api.jar hoặc orders-web.war |
| **Deployment slot** | Môi trường deployment riêng trong cùng app trên các tier hỗ trợ | staging |
| **Managed identity** | Danh tính của app truy cập dịch vụ Azure không cần lưu mật khẩu tĩnh | System-assigned identity |
| **Monitoring** | Log, metric, tracing và cảnh báo | Azure Monitor / Application Insights |

### 2.2. Web App khác App Service Plan như thế nào?

**Web App** định nghĩa ứng dụng bạn triển khai. **App Service Plan** quyết định region, hệ điều hành, SKU, số instance và năng lực compute mà app sử dụng.

~~~mermaid
flowchart TD
    RG["Resource group"] --> PLAN["App Service Plan<br/>Linux / một region / SKU"]
    PLAN --> A["Web App A<br/>Java SE JAR"]
    PLAN --> B["Web App B<br/>Tomcat WAR"]
    PLAN --> C["Web App C<br/>Java API khác"]
~~~

Nhiều ứng dụng có thể dùng chung một plan **khi cấu hình hỗ trợ**, nhưng cùng chia sẻ năng lực compute và đặc tính scale của plan. Một ứng dụng tiêu thụ CPU/memory quá nhiều có thể ảnh hưởng ứng dụng khác trên cùng plan.

**Dừng một Web App không tự dừng tính phí App Service Plan.** Nhiều gói trả phí tính phí theo năng lực instance của plan đã cấp, không theo số request hoặc thời gian Java process có người truy cập.

## 3. Chọn đúng kiểu triển khai: Java SE hay Java web?

### 3.1. Java SE với executable JAR

Kịch bản phổ biến: ứng dụng Spring Boot đóng gói thành **JAR tự chạy**, bao gồm dependency và web server nhúng cần thiết.

~~~text
Mã Java + dependency + embedded web server
                    |
                 Maven/Gradle
                    |
              orders-api.jar
                    |
          App Service: Java SE
                    |
          Java process lắng nghe HTTP
~~~

Ứng dụng khởi động qua entry point, ví dụ **public static void main(String[] args)**. JAR phải thực sự **executable**: có manifest/launcher phù hợp và các dependency cần thiết. Một thư viện JAR thông thường không đủ để chạy dịch vụ web.

**Phù hợp cho:** Spring Boot REST API, web service tự đóng gói, ứng dụng có embedded Tomcat/Jetty/Undertow hoặc embedded HTTP server tương thích.

### 3.2. Java web với WAR trong Tomcat

Kịch bản khác: ứng dụng dùng Servlet/Jakarta Servlet, JSP hoặc framework triển khai trong một servlet container có sẵn.

~~~text
Servlet / JSP / Framework web
              |
          Maven WAR
              |
         orders-web.war
              |
       App Service: Tomcat
              |
     Tomcat quản lý web context
~~~

Ứng dụng **WAR** không nhất thiết có một lệnh **java -jar** chạy độc lập. Tomcat cung cấp servlet container, lifecycle, context path và thành phần Java web theo phiên bản runtime.

**Phù hợp cho:** ứng dụng Servlet/JSP truyền thống, Spring MVC WAR hoặc ứng dụng cần được deploy như web archive lên Tomcat.

### 3.3. Bảng so sánh nhanh

| Tiêu chí | Java SE (executable JAR) | Java web (WAR/Tomcat) |
|---|---|---|
| Artifact | JAR tự chạy | WAR |
| Cách khởi động | Java main/launcher và web server nhúng | Tomcat triển khai web archive |
| Ai cung cấp web server? | Artifact/ứng dụng | Runtime Tomcat của nền tảng |
| Ví dụ | Spring Boot executable JAR | Servlet/JSP, Spring MVC WAR |
| Điều phải kiểm tra | Manifest, dependency, startup và HTTP port | Servlet API, Tomcat version, context path |
| Hành vi URL | Thường trực tiếp theo route ứng dụng | Có thể có context path theo tên WAR/cấu hình |
| Lỗi phổ biến | JAR không executable, bind sai port, process thoát | WAR sai phiên bản Servlet, 404 context, lỗi deploy |
| Khả năng cấu hình JVM | Theo runtime hỗ trợ và startup/settings | Theo runtime Tomcat, server settings và app settings |

Một ứng dụng **Spring Boot** có thể được đóng gói cả hai kiểu, nhưng cách build khác nhau. Đừng deploy một WAR rồi chọn Java SE như thể WAR là executable JAR; cũng đừng đưa executable JAR vào Tomcat rồi kỳ vọng tự động chạy đúng nếu không có cơ chế hỗ trợ.

### 3.4. JBoss EAP có giống Tomcat không?

Không. **JBoss Enterprise Application Platform (EAP)** là một ứng dụng server Java có hệ sinh thái và khả năng khác Tomcat. Nếu dự án dùng Jakarta EE APIs, EJB hoặc các tính năng enterprise server khác, phải đánh giá riêng:

- Loại runtime JBoss EAP và môi trường App Service hiện hỗ trợ.
- Phiên bản Java/Jakarta EE phù hợp.
- Định dạng WAR/EAR và phương thức triển khai được hỗ trợ.
- License, điều khoản sử dụng, SKU và chi phí.
- Các yêu cầu về startup, cấu hình và kết nối.

Bài này tập trung **Java SE/JAR** và **Tomcat/WAR** để minh họa hai đường triển khai cốt lõi.

## 4. Chọn môi trường chạy và phiên bản

### 4.1. Linux hay Windows?

App Service có những runtime Java được hỗ trợ trên Linux và Windows theo danh sách của Azure. Không nên giả định một tính năng hay phiên bản Tomcat có mặt ở cả hai hệ điều hành.

Cần xem:

1. Phiên bản JDK mà code và dependency hỗ trợ.
2. Runtime Java SE hoặc Tomcat hiện có trên OS định chọn.
3. Yêu cầu thư viện native, font, locale, file path, case sensitivity.
4. Cơ chế startup và logging riêng của runtime/OS.
5. Tính năng networking, deployment slot, scaling và plan SKU.
6. Yêu cầu licensing hoặc compliance.

Ví dụ CLI trong bài sử dụng **Linux App Service Plan**. Nếu ứng dụng đang phụ thuộc Windows Registry, .dll hoặc đường dẫn Windows, không nên di chuyển thẳng lên Linux mà chưa kiểm thử.

### 4.2. Phiên bản Java và Tomcat phải tương thích

Có ba phiên bản dễ nhầm:

- **Build JDK**: JDK dùng trong CI/Maven để compile.
- **Runtime JDK**: Java được cấu hình trong Web App.
- **Servlet/Tomcat API**: phiên bản container và namespace mà ứng dụng web dùng.

Lỗi thường gặp: build bằng bytecode Java mới hơn runtime → **UnsupportedClassVersionError**. Cách phòng ngừa là cấu hình **maven.compiler.release** hoặc toolchain phù hợp và đồng bộ với Java runtime ở App Service.

Riêng Tomcat:

- Ứng dụng cũ dùng **javax.servlet** không mặc nhiên tương thích với Tomcat thế hệ Jakarta dùng **jakarta.servlet**.
- Tomcat 10+ chuyển sang namespace Jakarta trong Servlet API. Việc đổi runtime có thể đòi hỏi migration code và dependency.
- Không lấy WAR build cho Tomcat 9 rồi deploy sang Tomcat 10.1 chỉ vì cả hai đều là “Tomcat”.

### 4.3. Không hard-code danh sách runtime từ tài liệu cũ

Phiên bản runtime/stack được Azure hỗ trợ có thể thay đổi. Cần kiểm tra **Azure Portal** hoặc danh sách CLI ngay trước khi tạo Web App:

~~~bash
az webapp list-runtimes --os linux --output table
~~~

Lệnh trả về các runtime identifier được hỗ trợ tại thời điểm kiểm tra. Chọn đúng giá trị cho **Java SE** hoặc **Tomcat** và đúng JDK; trong các ví dụ sau, thay các placeholder bằng chính chuỗi runtime được liệt kê, không tự đặt tên stack.

Với ứng dụng production, còn cần kế hoạch nâng cấp trước khi runtime hoặc framework hết hỗ trợ, kiểm tra vulnerability và thử nghiệm tích hợp sau nâng cấp.

## 5. Quy trình tổng thể từ source code đến production

~~~mermaid
flowchart TD
    S["Source + build config"] --> B["Compile, test, package"]
    B --> A{"Artifact?"}
    A -->|Executable JAR| J["App Service Java SE"]
    A -->|WAR| T["App Service Tomcat"]
    J --> C["App settings, identity, network"]
    T --> C
    C --> D["Deploy to staging / test"]
    D --> E["Smoke test + health check + logs"]
    E --> F{"Đạt?"}
    F -->|Có| P["Release production"]
    F -->|Không| R["Rollback / sửa lỗi"]
    R --> B
    P --> M["Monitor, scale, patch, tối ưu chi phí"]
~~~

Trước khi làm lab, phải xác định chính xác:

- **Artifact**: JAR hay WAR, tên file, version, dependency.
- **Runtime**: Java SE hay Tomcat, Java release, OS.
- **Cấu hình**: environment variables, connection endpoints, secrets.
- **Kết nối**: app có dùng SQL/Storage/Key Vault hay dịch vụ nội bộ không.
- **Health**: endpoint kiểm tra app đã sẵn sàng.
- **Release**: rollback khi bản mới khởi động lỗi.
- **Chi phí**: SKU/instance và tài nguyên phụ trợ.

## 6. Ví dụ A: ứng dụng Java SE dạng executable JAR

Để minh họa khác biệt về packaging, ta tạo một HTTP server nhỏ chỉ dùng JDK. Trong dự án thực, có thể thay nó bằng Spring Boot executable JAR được build bằng starter đã được kiểm thử của tổ chức.

### 6.1. Cấu trúc Maven

~~~text
orders-java-se/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── HealthServer.java
~~~

Maven project cần build một JAR có **Main-Class** và web server luôn lắng nghe cổng. Ví dụ dùng **JDK 17** để có mã ngắn gọn; khi triển khai phải chọn runtime Azure tương thích. Đây là ứng dụng demo, không phải web server production đầy đủ.

### 6.2. File HealthServer.java

~~~java
package com.example;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

public final class HealthServer {
    public static void main(String[] args) throws IOException {
        // Chỉ dùng PORT nếu môi trường runtime cung cấp biến này.
        // Mặc định 8080 là lựa chọn cho demo; phải kiểm tra port
        // được runtime App Service thực tế định tuyến.
        String configured = System.getenv("PORT");
        int port = configured == null || configured.isBlank()
                ? 8080 : Integer.parseInt(configured);

        HttpServer server = HttpServer.create(
                new InetSocketAddress("0.0.0.0", port), 0);

        server.createContext("/health", exchange -> {
            byte[] body = "{\"status\":\"UP\",\"runtime\":\"Java SE\"}"
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders()
                    .set("Content-Type", "application/json; charset=UTF-8");
            exchange.sendResponseHeaders(200, body.length);
            try (var output = exchange.getResponseBody()) {
                output.write(body);
            }
        });

        server.createContext("/", exchange -> {
            byte[] body = "Orders Java SE demo"
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders()
                    .set("Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, body.length);
            try (var output = exchange.getResponseBody()) {
                output.write(body);
            }
        });

        server.start();
        System.out.println("HTTP server is listening on port " + port);
    }
}
~~~

Điểm quan trọng:

- **0.0.0.0** cho phép process lắng nghe từ network namespace/container, không chỉ localhost.
- **/health** trả HTTP 200 khi demo có thể phục vụ.
- Process tiếp tục chạy sau khi **server.start()**, phù hợp với workload web.
- Code không chứa secret hoặc state cần tồn tại lâu dài trên local filesystem.
- Port **phải khớp cơ chế routing của Java SE stack trong App Service**. Biến **PORT** có thể được cung cấp/được cấu hình tùy môi trường; không giả định mọi stack hoặc custom container đều dùng cùng một biến.
- Với production, Spring Boot/servlet engine sẽ cung cấp nhiều khả năng HTTP, TLS behind proxy, graceful shutdown và observability hơn demo này.

### 6.3. File pom.xml để tạo executable JAR

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example</groupId>
  <artifactId>orders-java-se</artifactId>
  <version>1.0.0</version>
  <packaging>jar</packaging>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-jar-plugin</artifactId>
        <version>3.4.2</version>
        <configuration>
          <archive>
            <manifest>
              <mainClass>com.example.HealthServer</mainClass>
            </manifest>
          </archive>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Mẫu có thể dùng để minh họa quy trình; khi vận hành thật cần quản lý phiên bản plugin/JDK theo chính sách bảo mật và kiểm tra build environment.

### 6.4. Build và chạy thử tại máy

~~~bash
# Chạy trong thư mục orders-java-se/
mvn -B clean package

# Chạy bằng JDK tương thích
java -jar target/orders-java-se-1.0.0.jar
~~~

Ở terminal khác:

~~~bash
curl --fail --show-error http://localhost:8080/health
~~~

Kỳ vọng phản hồi:

~~~json
{"status":"UP","runtime":"Java SE"}
~~~

Trước khi triển khai, xác nhận artifact thực sự được tạo và chạy bằng Java release sẽ chọn trên App Service. **Không bắt đầu bằng cách upload source .java rồi mong App Service tự đoán mọi phụ thuộc và Main-Class**.

### 6.5. Spring Boot executable JAR khác gì ví dụ này?

Với ứng dụng REST thực tế dùng Spring Boot, đường đi thường là:

~~~text
@RestController + Spring Boot + dependency
              |
       mvn clean package
              |
      Spring Boot executable JAR
              |
         App Service Java SE
~~~

Spring Boot plugin thường đóng gói dependency/embedded server thành executable JAR với launcher phù hợp. Nếu đã có một Spring Boot project dùng trong đội, có thể triển khai JAR đó theo cùng luồng Java SE trong bài, nhưng phải kiểm tra:

- JDK build/runtime tương thích với Spring Boot version.
- Artifact thực sự là executable JAR, không phải thư viện JAR mỏng.
- HTTP port, startup/health, biến môi trường và profiles.
- Database connection, pool settings, logging và cách dừng có kiểm soát.
- Không nhúng credential trong file **application.properties** của artifact.

## 7. Ví dụ B: ứng dụng Java web dạng WAR cho Tomcat

Để phân biệt rõ JAR và WAR, ví dụ thứ hai dùng **Jakarta Servlet** và Maven WAR. Code sau minh họa cho servlet API tương thích với **Tomcat 10.1**; nếu runtime Tomcat có phiên bản API khác, phải điều chỉnh dependency và imports tương ứng.

### 7.1. Cấu trúc dự án

~~~text
orders-web/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── HealthServlet.java
~~~

### 7.2. Servlet mẫu

~~~java
package com.example;

import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

@WebServlet("/health")
public class HealthServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response) throws IOException {
        response.setStatus(HttpServletResponse.SC_OK);
        response.setContentType("application/json; charset=UTF-8");
        response.getWriter().write("{\"status\":\"UP\",\"runtime\":\"Tomcat\"}");
    }
}
~~~

Servlet **không có main method**. Tomcat nhận request, tìm mapping **/health** và gọi servlet tương ứng. Trong ứng dụng production, cần có authentication, validation, error handling và logging phù hợp.

### 7.3. POM cho WAR

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example</groupId>
  <artifactId>orders-web</artifactId>
  <version>1.0.0</version>
  <packaging>war</packaging>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>jakarta.servlet</groupId>
      <artifactId>jakarta.servlet-api</artifactId>
      <version>6.0.0</version>
      <scope>provided</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-war-plugin</artifactId>
        <version>3.4.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**Scope provided** thể hiện Tomcat cung cấp Servlet API khi chạy, tránh đóng gói trùng servlet API vào WAR. Nếu app dùng Spring MVC/Jakarta EE khác, dependency có thể phức tạp hơn.

### 7.4. Build WAR

~~~bash
# Chạy trong thư mục orders-web/
mvn -B clean package

# Kiểm tra file sinh ra trong target/
# Ví dụ: target/orders-web-1.0.0.war
~~~

WAR chứa các lớp, tài nguyên và metadata web app; Tomcat sẽ triển khai archive và quản lý lifecycle.

### 7.5. Context path và ROOT.war

Tomcat thường tổ chức web app theo context path. Trong một số cấu hình triển khai:

- WAR có tên **orders-web.war** có thể được truy cập dưới context **/orders-web**.
- WAR triển khai dưới tên **ROOT.war** hoặc target root được runtime hỗ trợ có thể cung cấp context **/**.

Với App Service, cách deployment tool đặt WAR vào Tomcat và cơ chế root context có thể phụ thuộc runtime/target path. **Hãy kiểm tra context URL thực tế sau triển khai**, thay vì tự kết luận cứ upload file nào cũng trả về **/health** ở root.

Nếu bị HTTP 404, hãy kiểm tra WAR deployment logs và context path trước khi đổi NSG hoặc database firewall.

## 8. Chuẩn bị tài nguyên Azure cho lab

Các ví dụ dưới đây **không được chạy tự động trong bài học**. Chúng minh họa lệnh dành cho một subscription/resource group thực hành mà bạn có quyền quản lý. Thay các placeholder, kiểm tra region/SKU/quota và chi phí trước khi chạy.

### 8.1. Điều kiện tiên quyết

- Có Azure subscription và quyền tạo resource group, App Service Plan, Web App.
- Máy build có **JDK**, **Maven** và Azure CLI phiên bản được hỗ trợ.
- Artifact JAR/WAR đã chạy thành công tại local.
- Chọn region có Linux App Service và runtime cần dùng.
- Tên Web App **duy nhất trong namespace dịch vụ** để có hostname phù hợp.
- Có quyền triển khai app nhưng không nhất thiết phải Owner toàn subscription.
- Xác định có dùng database/Storage/Key Vault hoặc VNet Integration hay không.
- Có ngân sách lab và kế hoạch xóa tài nguyên sau thực hành.

### 8.2. Đăng nhập và tạo resource group

~~~bash
az login
az account set --subscription "<subscription-id>"
az account show --output table

RG="rg-java-app-lab"
LOCATION="southeastasia"

az group create \
  --name "$RG" \
  --location "$LOCATION"
~~~

Resource group là phạm vi quản lý và có region metadata riêng, không có nghĩa mọi tài nguyên bên trong bắt buộc cùng region. App Service Plan và Web App phải tuân theo quy tắc region/OS của dịch vụ.

### 8.3. Tạo Linux App Service Plan

~~~bash
PLAN="asp-java-linux-lab"

az appservice plan create \
  --name "$PLAN" \
  --resource-group "$RG" \
  --location "$LOCATION" \
  --sku B1 \
  --is-linux
~~~

Đây là **Basic B1** cho lab; giá và khả năng hỗ trợ có thể thay đổi theo region. Tier nhỏ có giới hạn compute, memory, scaling và deployment features. Nếu workload có yêu cầu **deployment slots**, zone redundancy hoặc scaling nâng cao, phải chọn plan/SKU đáp ứng tính năng cụ thể.

**App Service Plan có thể bắt đầu phát sinh phí khi được tạo ngay cả khi chưa có request đến ứng dụng.**

## 9. Tạo và triển khai Web App Java SE bằng Azure CLI

### 9.1. Chọn đúng runtime Java SE

~~~bash
az webapp list-runtimes --os linux --output table
~~~

Đối chiếu với runtime được hỗ trợ trong region/OS và phiên bản JDK đã build. Sau đó:

~~~bash
JAVA_SE_RUNTIME="<exact-Java-SE-runtime-id-from-list>"
JAVA_SE_APP="<globally-unique-java-se-webapp-name>"

az webapp create \
  --resource-group "$RG" \
  --plan "$PLAN" \
  --name "$JAVA_SE_APP" \
  --runtime "$JAVA_SE_RUNTIME"
~~~

Ví dụ placeholder **JAVA_SE_RUNTIME** phải là chuỗi nguyên dạng từ lệnh list-runtimes; **không** tự thay bằng tên mơ hồ như “Java 17” nếu CLI yêu cầu identifier khác.

### 9.2. Thiết lập app settings không nhạy cảm

~~~bash
az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$JAVA_SE_APP" \
  --settings APP_ENV=lab
~~~

Các app settings của App Service được cung cấp cho runtime dưới dạng biến môi trường theo cơ chế nền tảng. Trong Java có thể đọc:

~~~java
String environment = System.getenv("APP_ENV");
~~~

Đối với secret, không đưa mật khẩu trực tiếp vào command history, shell script, pipeline log hoặc Git. Hãy xem phần Key Vault/managed identity.

### 9.3. Triển khai executable JAR

~~~bash
az webapp deploy \
  --resource-group "$RG" \
  --name "$JAVA_SE_APP" \
  --src-path "target/orders-java-se-1.0.0.jar" \
  --type jar
~~~

Lệnh này giả định bạn đang đứng tại thư mục Maven project chứa artifact đã build. Loại **jar** phải phù hợp với runtime Java SE.

Tùy runtime và phương thức deployment, App Service có cơ chế tự xác định artifact để khởi động. **Nếu ứng dụng không tự start**, phải xem startup logs, vị trí artifact trên server và hỗ trợ startup command của đúng stack/OS; không tự đặt một đường dẫn cố định khi chưa kiểm chứng nơi artifact được giải nén/đặt.

### 9.4. Xem cấu hình và hostname

~~~bash
az webapp show \
  --resource-group "$RG" \
  --name "$JAVA_SE_APP" \
  --query "{name:name,state:state,host:defaultHostName,location:location}" \
  --output json

az webapp config show \
  --resource-group "$RG" \
  --name "$JAVA_SE_APP" \
  --query "{linuxFxVersion:linuxFxVersion,alwaysOn:alwaysOn,appCommandLine:appCommandLine}" \
  --output json
~~~

Các trường thực tế có thể thay đổi theo OS/API và phiên bản CLI. Từ kết quả hostname, xây URL HTTPS của ứng dụng:

~~~bash
curl --fail --show-error \
  "https://<globally-unique-java-se-webapp-name>.azurewebsites.net/health"
~~~

Mong đợi phản hồi status UP khi Java process chạy đúng cổng và request được route đến app. Nếu thấy trang mặc định, timeout hoặc HTTP 5xx, cần kiểm tra deployment, process startup, port và logs.

### 9.5. Khi nào cần startup command?

Với một số ứng dụng Java SE, có thể phải cấu hình **startup command** hoặc điều chỉnh runtime khi cần JVM options, classpath hay quy tắc khởi động đặc biệt.

Nguyên tắc an toàn:

1. Xem startup behavior mặc định của runtime Java SE đang dùng.
2. Xem deploy log để biết artifact thực sự được đặt ở đâu.
3. Kiểm tra cách runtime chọn JAR, startup command và port.
4. Chỉ đặt command tùy chỉnh nếu cần và đã thử trong staging.
5. Không đưa secret vào command.
6. Kiểm tra app vẫn chạy sau restart và scale-out.

Không dùng một command cố định kiểu **java -jar /some/guessed/path/app.jar** nếu không biết đường dẫn trên instance. Cũng không dùng background process thoát khỏi startup script mà không giữ web server hoạt động.

## 10. Tạo và triển khai Web App Tomcat/WAR bằng Azure CLI

### 10.1. Tạo Web App chạy Tomcat

~~~bash
az webapp list-runtimes --os linux --output table
~~~

Chọn runtime **Tomcat** tương thích với Java release và Jakarta Servlet API đang dùng, ví dụ thế hệ Tomcat hỗ trợ **jakarta.servlet** của dự án. Không dùng lựa chọn Java SE cho WAR của ví dụ này.

~~~bash
TOMCAT_RUNTIME="<exact-Tomcat-runtime-id-from-list>"
TOMCAT_APP="<globally-unique-tomcat-webapp-name>"

az webapp create \
  --resource-group "$RG" \
  --plan "$PLAN" \
  --name "$TOMCAT_APP" \
  --runtime "$TOMCAT_RUNTIME"
~~~

Có thể dùng chung plan cho cả hai app trong lab để minh họa, nhưng chúng **chia sẻ CPU/memory**. Với hệ thống quan trọng, cân nhắc tách plan theo tải, ranh giới triển khai hoặc yêu cầu bảo mật.

### 10.2. Triển khai WAR

~~~bash
az webapp deploy \
  --resource-group "$RG" \
  --name "$TOMCAT_APP" \
  --src-path "target/orders-web-1.0.0.war" \
  --type war
~~~

Lệnh giả định đang chạy từ thư mục dự án WAR có artifact tương ứng. Sau khi triển khai:

1. Xem log deployment và log Tomcat.
2. Kiểm tra tên web application/context path đã được tạo.
3. Gọi endpoint /health dưới context thực tế.
4. Xác nhận lỗi package namespace và các dependency không xuất hiện.
5. Kiểm tra startup time và readiness trước khi mở traffic production.

Ví dụ kiểm tra với context được deploy theo tên archive:

~~~bash
curl -i \
  "https://<globally-unique-tomcat-webapp-name>.azurewebsites.net/orders-web-1.0.0/health"
~~~

**URL này chỉ minh họa**, không phải cam kết rằng deployment bằng CLI nhất định đặt context path theo tên đó. Nếu App Service triển khai WAR thành root context, endpoint có thể là **/health**. Hãy lấy context thực tế từ runtime/deployment logs; nếu cần root, sử dụng phương thức deployment/target path được Microsoft hỗ trợ và kiểm thử sau khi đổi.

### 10.3. Triển khai WAR của Spring Boot

Nếu một dự án Spring Boot đang xuất executable JAR mà muốn deploy vào Tomcat bên ngoài, thường phải sửa cấu hình build và bootstrap ứng dụng:

- Chuyển packaging sang **war**.
- Cấu hình servlet container dependency là **provided** theo hướng dẫn Spring Boot.
- Có entry point cho servlet container, thường là class mở rộng **SpringBootServletInitializer**.
- Kiểm tra Spring Boot version và Servlet API/Jakarta namespace tương thích Tomcat.
- Kiểm tra static resources, context path và filters.
- Build/test WAR trong phiên bản Tomcat tương đương trước khi triển khai.

Không chỉ đổi phần mở rộng **.jar → .war** bằng rename. Định dạng archive và lifecycle khởi động là hai cơ chế khác nhau.

## 11. Azure Portal: triển khai cùng bài toán

Với Portal, có thể tạo ứng dụng Java SE hoặc Tomcat mà không cần viết CLI ngay từ đầu.

### 11.1. Tạo Web App

1. Mở **Azure Portal → App Services → Create → Web App**.
2. Chọn subscription, resource group và tên ứng dụng.
3. Chọn **Publish: Code** nếu sẽ triển khai artifact/runtime tích hợp.
4. Chọn runtime stack phù hợp: **Java** cho Java SE hoặc **Tomcat** khi Portal cung cấp lựa chọn tương ứng.
5. Chọn đúng phiên bản Java và OS được hỗ trợ.
6. Chọn region và một App Service Plan phù hợp; đọc giới hạn và chi phí.
7. Kiểm tra các trang networking, monitoring, deployment và cấu hình bảo mật.
8. Review, triển khai và chờ Web App được tạo.
9. Mở **Overview**, ghi lại default hostname và runtime settings.

Tên menu có thể thay đổi khi Portal cập nhật. Các runtime cụ thể phụ thuộc OS/region/tier.

### 11.2. Đưa artifact lên

Có nhiều cơ chế như CLI deployment, IDE plugin, CI/CD hoặc deployment center. Khi chọn:

- **Executable JAR:** dùng deployment type **JAR**, cấu hình Java SE runtime.
- **WAR:** dùng phương thức **WAR deployment** tới Tomcat.
- **Source deployment:** chỉ khi builder/Oryx/CI được cấu hình rõ để tạo artifact.
- **Container image:** là luồng **custom container** riêng; phải cung cấp image, registry, runtime, listening port và cách khởi động theo yêu cầu container.

Để bài học tái lập được, hãy lưu artifact version và deployment record; không thao tác kéo-thả không có lịch sử hoặc không biết mã build.

## 12. Cấu hình môi trường: App settings và connection strings

### 12.1. Vì sao phải tách cấu hình khỏi artifact?

Một artifact được kiểm thử nên có thể deploy vào **dev**, **staging** và **production** mà không phải sửa source để thay endpoint hoặc credential.

Ví dụ:

| Cấu hình | Dev | Production |
|---|---|---|
| APP_ENV | dev | prod |
| API_BASE_URL | URL kiểm thử | URL production |
| DB_HOST | Database dev | Database production |
| LOG_LEVEL | DEBUG hoặc INFO có kiểm soát | INFO/WARN theo chính sách |
| Secret | Secret từ Key Vault dev | Secret từ Key Vault production |

Dữ liệu nhạy cảm không nên hard-code trong **pom.xml**, Java class, **application.properties** được commit hoặc shell history.

### 12.2. App settings và biến môi trường

~~~bash
az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$JAVA_SE_APP" \
  --settings APP_ENV=dev LOG_LEVEL=INFO
~~~

Trong Java:

~~~java
String env = System.getenv("APP_ENV");
String logLevel = System.getenv("LOG_LEVEL");
~~~

Lưu ý:

- App settings có thể làm app restart khi thay đổi.
- Biến môi trường phân biệt cách đặt tên và xử lý của framework.
- **Spring Boot** có cơ chế map environment variables sang cấu hình của framework; cần kiểm tra precedence giữa app settings, command line và profiles.
- Khi dùng slot, đánh dấu setting nào là **deployment slot setting** để tránh swap nhầm credential/endpoint production và staging.
- Không dùng Azure Portal để sửa live setting mà quên đồng bộ source of truth của IaC/pipeline.

### 12.3. Managed identity và Key Vault

Một mô hình an toàn hơn credential tĩnh:

~~~mermaid
flowchart LR
    A["App Service Java"] -->|"Managed identity token"| I["Microsoft Entra ID"]
    I -->|"Access token"| A
    A -->|"Đọc secret theo RBAC"| K["Azure Key Vault"]
    A -->|"SDK Azure và RBAC"| S["Storage / Database"]
~~~

Quy trình:

1. Bật **system-assigned** hoặc **user-assigned managed identity** cho Web App.
2. Cấp role **tối thiểu** trên dịch vụ đích đúng scope.
3. Dùng Azure SDK và cơ chế credential phù hợp, ví dụ **DefaultAzureCredential**, khi dịch vụ hỗ trợ.
4. Với giá trị secret cần đưa vào app setting, có thể dùng **Key Vault references** theo hướng dẫn App Service.
5. Xác minh kết nối trong staging; theo dõi lỗi 401/403 và các thay đổi quyền.

Ví dụ bật identity:

~~~bash
az webapp identity assign \
  --resource-group "$RG" \
  --name "$JAVA_SE_APP"
~~~

Bật identity **chưa tự cấp quyền** đọc secret trong Key Vault. Role assignment/policy phải được cấu hình riêng, được phê duyệt và đúng data-plane permission.

### 12.4. Cấu hình cổng HTTP

App Service có reverse proxy/frontend đưa request về ứng dụng. Java process phải lắng nghe **đúng cổng** theo stack/OS đã chọn, và phải bind đến interface có thể nhận traffic.

- Với framework như Spring Boot, kiểm tra **server.port** và cách lấy port theo runtime.
- Với Java SE custom startup, xem biến môi trường và hướng dẫn port của stack được Azure cung cấp.
- Với Tomcat built-in, tránh tự override port của server mà không cần.
- Với custom container, có các quy tắc riêng về exposed/listening port và app settings như **WEBSITES_PORT** khi phù hợp.

Một chương trình chỉ bind **127.0.0.1** hoặc cổng mà App Service không route đến có thể chạy trong process nhưng liên tục trả HTTP 502/503 ở public endpoint.

## 13. Logging, health checks và quan sát ứng dụng

### 13.1. Đặt health endpoint phù hợp

Đối với cả hai ví dụ, endpoint **/health** cho phép xác nhận ứng dụng trả HTTP 200. Trong production, nên phân biệt:

- **Liveness:** tiến trình/ứng dụng còn hoạt động.
- **Readiness:** ứng dụng có thể nhận traffic nghiệp vụ.
- **Dependency health:** database, queue, cache hoặc dịch vụ phụ thuộc có sẵn sàng không.

Không bắt mọi dependency phụ phải Healthy cho một liveness probe nếu điều đó gây vòng lặp restart không cần thiết. Health endpoint cần trả dữ liệu tối thiểu, không rò thông tin cấu hình, đường dẫn nội bộ hoặc secret.

### 13.2. Application logs và platform logs

Khi deployment gặp lỗi, phân biệt:

| Loại log | Câu hỏi |
|---|---|
| Deployment/build log | Artifact có được upload và triển khai thành công không? |
| Startup/console log | JVM có chạy không, exception gì khi khởi động? |
| Tomcat log | WAR có deploy vào đúng context không, Servlet API có tương thích không? |
| Application log | Endpoint trả 500 vì code, SQL, cấu hình hay dependency? |
| HTTP access log | Request đến server, status code, latency thế nào? |
| Azure Activity Log | Ai đã thay settings, runtime, scale hoặc restart? |
| Application Insights | Request telemetry, dependency calls, exceptions, distributed traces theo cấu hình |

Nếu phù hợp, có thể xem log stream qua Portal hoặc CLI:

~~~bash
az webapp log tail \
  --resource-group "$RG" \
  --name "$JAVA_SE_APP"
~~~

Log streaming cần bật logging tương ứng và phải được hỗ trợ bởi OS/runtime/deployment. Nếu lệnh không hiện gì, điều đó **không chứng minh ứng dụng không có lỗi**; kiểm tra Diagnostic settings, log stream và công cụ giám sát khác.

### 13.3. Application Insights và Azure Monitor

Với production, cấu hình instrumentation Java qua cơ chế Azure hỗ trợ để theo dõi:

- Request rate, status 4xx/5xx, latency p50/p95/p99.
- Exception theo loại và thời điểm.
- Dependency calls tới database, HTTP API, Storage.
- CPU, memory, instance count của App Service Plan/Web App.
- Startup failures, restarts, health check và availability test.
- Alert khi lỗi tăng, response time bất thường hoặc instance không healthy.

Quản lý sampling, retention, PII và giá ingestion. **Không ghi password, access token, connection string hoặc dữ liệu khách hàng nhạy cảm** vào log.

## 14. Triển khai bản mới và rollback an toàn

### 14.1. Không triển khai thẳng production khi chưa smoke test

Pipeline nên có các chặng:

~~~mermaid
flowchart LR
    C["Git commit"] --> B["Maven build"]
    B --> T["Unit + integration tests"]
    T --> S["Security/dependency scan"]
    S --> A["Versioned JAR/WAR"]
    A --> D["Deploy staging"]
    D --> H["Health/smoke tests"]
    H --> P["Promote / swap production"]
    P --> M["Monitor error rate và latency"]
    M --> R{"Release ổn?"}
    R -->|Không| RB["Rollback theo runbook"]
~~~

Một deployment được ghi nhận thành công chỉ cho biết artifact đã đến môi trường hoặc quá trình triển khai đã kết thúc thành công. Nó **không bảo đảm ứng dụng đã đạt readiness** hay các route nghiệp vụ hoạt động.

### 14.2. Deployment slots

Với những App Service Plan tier hỗ trợ deployment slots, có thể tạo **staging slot**, triển khai phiên bản mới tại đó, kiểm thử và **swap** sang production khi đạt yêu cầu.

Ưu điểm:

- Kiểm thử bản build trong môi trường gần production.
- Khả năng warm-up ứng dụng trước khi chuyển traffic theo tính năng hỗ trợ.
- Có đường quay lại phiên bản trước khi gặp sự cố.

Lưu ý:

- Không phải tier nào cũng có deployment slots; **Basic B1 lab trong bài không dùng slot production như một giả định sẵn có**.
- Slots chia sẻ năng lực compute của plan và có thể tăng memory/CPU pressure.
- App settings có thể là slot-specific hoặc được swap tùy cấu hình.
- Swap không tự rollback thay đổi database schema hoặc dữ liệu.
- Cần kiểm tra session, cache, request đang xử lý và background jobs.

### 14.3. Tại sao database migration cần tách khỏi rollback artifact?

Giả sử release mới của Orders API thêm một cột và thay đổi định dạng dữ liệu. Nếu deployment WAR/JAR được rollback, database không tự quay về schema cũ. Một rollback code có thể thất bại nếu schema đã bị đổi không tương thích.

Cách giảm rủi ro:

1. Dùng thay đổi database **backward-compatible** khi có thể.
2. Tách migration và code rollout thành các bước có kiểm soát.
3. Theo dõi phiên bản schema và kiểm thử rollback.
4. Có backup/snapshot theo cơ chế database phù hợp.
5. Thực hiện smoke tests đối với cả API và luồng ghi/đọc dữ liệu.

## 15. Scaling, memory và JVM

### 15.1. Scale up và scale out

- **Scale up:** đổi tier/size của App Service Plan để có thêm năng lực mỗi instance.
- **Scale out:** tăng số instance phục vụ ứng dụng trong giới hạn plan.
- **Autoscale:** điều chỉnh instance theo metric/lịch khi SKU và dịch vụ hỗ trợ.

Không phải mọi plan/OS đều hỗ trợ cùng mô hình autoscale hoặc instance count. Trước khi triển khai production, xác minh quota, giới hạn, availability và tính phí.

### 15.2. JVM memory không bằng tổng RAM của plan

Java có heap, metaspace, thread stacks, native memory, code cache và các vùng nhớ khác. Nếu đặt **-Xmx** quá cao so với memory thực tế của instance, JVM hoặc container/process có thể bị kill vì memory pressure.

Cần đo:

- Heap usage và garbage collection pause.
- Non-heap/native memory, thread count.
- Request concurrency và connection pool.
- Mức memory khi app warm-up và khi tải cao.
- Memory tổng khi nhiều Web App dùng chung plan.
- Các startup flags JVM được runtime App Service hỗ trợ.

Không sao chép một giá trị JVM heap bất kỳ từ VM có nhiều RAM sang App Service Plan B1 nhỏ.

### 15.3. Stateless để scale tốt

Khi scale out, request của một người dùng có thể được phục vụ bởi nhiều instance. Vì vậy:

- Tránh lưu business data độc nhất trên local filesystem của Web App.
- Dùng Azure Storage, database, Redis hoặc dịch vụ lưu trạng thái phù hợp.
- Không dựa vào biến static/in-memory để lưu session chung cho mọi instance.
- Dùng cơ chế session affinity chỉ khi hiểu trade-off; tốt hơn là thiết kế phân phối trạng thái rõ ràng.
- Thực hiện retry, idempotency và graceful shutdown cho request đang xử lý.

Với Java web WAR, Tomcat session trong bộ nhớ cũng không tự đồng bộ giữa các instance App Service.

## 16. File system, artifact và persistent data

App Service cung cấp filesystem cho runtime/deployment, nhưng không nên coi máy chạy ứng dụng là một file server bền vững.

### 16.1. Không ghi dữ liệu quan trọng cạnh artifact

Các thư mục của nội dung ứng dụng như **wwwroot** có thể chịu ảnh hưởng của deploy, scale hoặc mode triển khai. Temp directory thường không bảo đảm tồn tại qua restart/recycle.

Ứng dụng không nên:

- Ghi hồ sơ khách hàng duy nhất vào thư mục project.
- Giữ user-uploaded files duy nhất trên local disk.
- Phụ thuộc dữ liệu chỉ nằm trong cache của một instance.
- Thay đổi file trong deployment package rồi mong các instance khác thấy thay đổi.

Thay vào đó, dùng Azure Blob Storage/Azure Files hoặc database phù hợp; xác định retention, backup và access control riêng.

### 16.2. Khi Java cần thư mục tạm

Có thể sử dụng thư mục tạm để xử lý request ngắn hạn, nhưng phải:

1. Có quota và cleanup.
2. Không lưu secret không được bảo vệ.
3. Xử lý trường hợp instance restart làm mất file tạm.
4. Không dùng file temp làm kênh trao đổi giữa các instance.
5. Giám sát disk pressure và I/O.

### 16.3. Build artifacts phải được version hóa

Một release nên truy vết được:

~~~text
Git commit:     <commit-id>
Artifact:       orders-api-1.4.2.jar
Build JDK:      phiên bản đã được phê duyệt
App runtime:    Java SE runtime tương thích
Environment:    staging / production
Deployment:     <deployment-id-or-pipeline-run>
Smoke test:     PASS / FAIL
~~~

Ghi thông tin này vào pipeline và phát hành, không nhúng token hoặc secret vào artifact metadata công khai.

## 17. Networking: Internet ingress và VNet Integration

Một Web App có thể công khai endpoint HTTPS, đồng thời cần kết nối riêng tới SQL/Storage trong VNet.

### 17.1. Inbound và outbound là hai việc khác nhau

- **Inbound:** client gửi request đến Web App thông qua endpoint, custom domain hoặc dịch vụ reverse proxy.
- **Outbound:** Web App gọi database, Storage, Key Vault hoặc hệ thống nội bộ.
- **VNet Integration:** chủ yếu phục vụ **outbound connectivity từ app** vào tài nguyên qua VNet theo khả năng hỗ trợ.
- **Private Endpoint cho App Service:** liên quan đến **private inbound access** vào Web App khi dịch vụ/tier hỗ trợ.

**Chỉ cấu hình VNet Integration không tự biến endpoint public của Web App thành private.** Cũng không mặc định Private Endpoint dành cho database sẽ hoạt động nếu DNS/route của app chưa phù hợp.

### 17.2. Ví dụ ứng dụng dùng Azure SQL Database

Mô hình:

~~~mermaid
flowchart LR
    C["Client"] -->|"HTTPS"| W["App Service Java API"]
    W -->|"VNet Integration (outbound)"| V["Integration subnet / VNet"]
    V -->|"Private IP / private DNS"| P["Private Endpoint của SQL"]
    P --> D["Azure SQL Database"]
~~~

Trước khi triển khai:

1. Xác nhận plan/tier/region và VNet Integration hỗ trợ.
2. Thiết kế subnet dành cho integration theo yêu cầu.
3. Cấu hình Private Endpoint và private DNS cho dịch vụ đích nếu dùng.
4. Thiết kế Azure RBAC/Entra authentication hoặc database identity.
5. Test DNS resolution và TCP connectivity từ môi trường ứng dụng.
6. Không mở SQL firewall cho **0.0.0.0/0** chỉ để “thử cho chạy”.

### 17.3. Bảo vệ ingress production

Cân nhắc theo yêu cầu:

- HTTPS only và TLS phù hợp.
- Custom domain và certificate có vòng đời quản lý.
- Access restrictions để thu hẹp nguồn truy cập.
- Private Endpoint cho Web App khi muốn private ingress theo khả năng hỗ trợ.
- Application Gateway/WAF hoặc Azure Front Door cho reverse proxy, bảo vệ HTTP và routing toàn cục.
- Authentication/Authorization trên App Service hoặc trong ứng dụng.
- Network path và DNS của service-to-service traffic.

Không cho rằng WAF, TLS và RBAC có thể thay thế lẫn nhau. Một hệ thống vẫn cần application-level authorization cho từng endpoint và dữ liệu.

## 18. Bảo mật dependency, secrets và supply chain

Triển khai JAR/WAR đưa không chỉ mã của bạn lên Azure mà còn cả các thư viện được build cùng artifact.

### 18.1. Kiểm tra dependency

- Khóa version dependency theo quy trình của tổ chức.
- Dùng công cụ quét CVE/SCA phù hợp trong pipeline.
- Kiểm tra thư viện transitively bundled.
- Cập nhật JDK/framework/Tomcat theo lịch và khi có lỗ hổng quan trọng.
- Sinh SBOM khi quy trình supply-chain yêu cầu.
- Kiểm tra license và repository artifacts được phê duyệt.

Với WAR, **provided** dependencies phải tương thích runtime Tomcat thực tế. Với JAR, embedded server và dependency là trách nhiệm của artifact, không chỉ của runtime Azure.

### 18.2. Quyền deploy không nên là quyền Owner

CI/CD chỉ cần quyền triển khai vào Web App/slot hoặc artifact endpoint phù hợp. Dùng cơ chế danh tính liên kết/OIDC hoặc managed identity/service principal khi được hỗ trợ, thay vì lưu publishing password lâu dài.

Không đưa **publish profile** chứa credential vào repo hay log. Tạo riêng danh tính cho từng environment và giới hạn scope.

### 18.3. Kiểm tra dữ liệu bị lộ

- Không để health endpoint in biến môi trường.
- Không bật debug mode nhạy cảm trên production.
- Không ghi connection string vào log khi khởi động thất bại.
- Không public swagger/admin console mà chưa có authentication.
- Không lưu dữ liệu người dùng trong temp không kiểm soát.
- Có quy trình revoke/rotate secret và kiểm tra authorization.

## 19. So sánh chiến lược deployment

| Cách triển khai | Đầu vào | Khi phù hợp | Điểm cần kiểm tra |
|---|---|---|---|
| **Azure CLI deploy JAR** | Executable JAR | Java SE API hoặc web server nhúng | Startup, port, dependencies |
| **Azure CLI deploy WAR** | WAR | Tomcat Servlet/JSP/MVC | Tomcat version, context path, Servlet namespace |
| **IDE plugin** | Build artifact từ dự án | Developer trải nghiệm nhanh | Cấu hình runtime và quyền deploy |
| **Maven deployment plugin** | Maven project/artifact | Tích hợp build và deploy | Plugin version, auth, settings và artifact type |
| **CI/CD** | Versioned JAR/WAR | Production có kiểm soát | Tests, secrets, approvals, rollback |
| **Custom container** | OCI image | Runtime/custom OS phức tạp | Image security, registry, port, startup và lifecycle |
| **Source deployment** | Source code | Khi build pipeline hỗ trợ rõ ràng | Build command, artifact reproducibility |

**Không trộn artifact loại này với stack loại khác chỉ vì Azure có thể chấp nhận upload file.** Tạo Web App đúng runtime trước, deploy đúng artifact và dùng endpoint health để xác minh.

## 20. Chi phí App Service và tối ưu hợp lý

### 20.1. App Service Plan là đơn vị compute được tính phí

Một Web App có thể không nhận request trong nhiều giờ, nhưng App Service Plan trả phí vẫn giữ năng lực compute theo tier/instance count. Vì vậy:

- Không nhầm **az webapp stop** với **az vm deallocate**.
- Stop một Web App không tự deallocate toàn bộ plan theo cách VM.
- Nếu nhiều app cùng plan, mức phí compute của plan thường được chia sẻ chứ không phải một phí VM độc lập cho từng app.
- Chi phí có thể thay đổi khi scale up/out, thay SKU hoặc dùng thêm plan ở region khác.
- Có thể có khoản phí riêng cho Application Insights, log storage, database, Storage Account, Front Door, Key Vault, NAT Gateway và các dịch vụ phụ trợ.

Một App Service Plan chỉ dành cho lab nhưng bị quên sau buổi thực hành vẫn có thể phát sinh phí dù app không có người dùng.

### 20.2. Ba cách tối ưu chính

1. **Right-size plan**: đo CPU, memory, requests, startup và latency trước khi chọn tier.
2. **Share plan khi hợp lý**: gom nhiều app tải nhẹ, nhưng tránh để một app gây ảnh hưởng app khác.
3. **Scale theo nhu cầu**: dùng autoscale theo metric/lịch khi tier hỗ trợ, không phóng to cố định mà không có dữ liệu.

Với workload chỉ chạy tác vụ một lần rồi kết thúc, hãy đánh giá Azure Functions, Azure Container Apps jobs hoặc dịch vụ batch phù hợp; App Service không phải lúc nào cũng tiết kiệm cho process không phục vụ HTTP liên tục.

### 20.3. Giám sát chi phí

Trong Azure Cost Management:

- Chọn đúng subscription/resource group.
- Nhóm theo service/resource/meter theo dữ liệu khả dụng.
- So sánh chi phí App Service Plan với database, storage, logs và network.
- Kiểm tra instance count/SKU thay đổi trong kỳ.
- Gắn tag owner/environment và ngân sách cho lab.
- Có quy trình tắt lab và dọn tài nguyên đúng quyền.

Không dùng một đơn giá cố định khi chưa xác minh region, plan và ngày áp dụng.

## 21. Khả năng sẵn sàng, zone và disaster recovery

Một App Service Web App được triển khai thành công không có nghĩa kiến trúc đã đáp ứng yêu cầu HA/DR.

### 21.1. Một instance và nhiều instance

Một instance có thể đủ cho lab; production cần đánh giá:

- Availability SLA điều kiện nào áp dụng với plan/tier.
- Có yêu cầu đa instance, health checking và autoscale không.
- Zone redundancy nếu region/SKU/plan hỗ trợ.
- Dữ liệu trạng thái có nằm bên ngoài instance không.
- Database/Storage có redundancy và backup phù hợp không.

Scale-out tăng số instance trong mô hình được hỗ trợ, nhưng không thay thế bảo vệ dữ liệu và kiểm thử failover.

### 21.2. Disaster recovery đa region

Nếu business yêu cầu phục hồi khi toàn bộ region bị sự cố, thường phải có:

- App Service Plan/Web App hoặc phương án triển khai sẵn ở region dự phòng.
- Artifact và cấu hình được quản lý để redeploy giống nhau.
- Database/storage replication/backup theo RPO.
- DNS hoặc traffic manager/front-end routing có thể chuyển người dùng.
- Key Vault, managed identity, networking và external dependencies ở region phụ.
- Runbook, diễn tập, rollback và quy trình đối chiếu dữ liệu.

Không tự xem deployment slots là DR đa region. Slots thường thuộc cùng app/plan/region và phục vụ release/rollback, không thay thế region failover.

## 22. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| JAR upload thành công nhưng web trả 502/503 | JVM/process chưa chạy, sai port, crash sau startup | Xem startup log, port, Main-Class, dependency |
| Java SE JAR không chạy | Chỉ là library JAR, thiếu launcher hoặc Main-Class | Chạy **java -jar** local, kiểm tra packaging |
| **UnsupportedClassVersionError** | Build JDK cao hơn runtime được chọn | So sánh bytecode target với runtime JDK |
| **ClassNotFoundException** | Thiếu dependency hoặc classpath | Kiểm tra fat JAR/Spring Boot packaging, WAR lib và scope |
| Tomcat WAR trả 404 | Sai context path, servlet mapping hoặc deploy lỗi | Xác nhận deployment/context và route |
| Tomcat WAR không load servlet | javax/jakarta mismatch hoặc Servlet API không tương thích | Chọn Tomcat đúng phiên bản, migration package |
| Web App hiện trang mặc định | Artifact chưa deploy đúng hoặc startup không trỏ app | Kiểm tra deploy history, nội dung và runtime |
| Local chạy được nhưng cloud không kết nối SQL | Network/DNS/identity hoặc firewall | Kiểm tra VNet Integration, private endpoint/DNS, credentials |
| 401/403 khi gọi Key Vault/Storage | Managed identity chưa có role đúng hoặc token/scope sai | Kiểm tra role assignment, SDK và data-plane permission |
| JVM bị kill hoặc restart liên tục | Memory vượt giới hạn, startup quá nặng | Kiểm tra heap/GC, native memory, SKU và logs |
| HTTP 503 khi deploy | Restart/recycle, health chưa đạt hoặc cấu hình không hợp lệ | Staging, warm-up, startup logs, rollback |
| Một số request lỗi sau scale-out | Local session/file cache không chia sẻ | Dùng external state, kiểm tra session/DB pool |
| Application settings bị đổi khi swap | Slot settings chưa được cấu hình đúng | Review sticky settings và release checklist |
| App Service vẫn tính phí khi app đã stop | Plan compute vẫn tồn tại | Kiểm tra App Service Plan, SKU/instance và billing |
| Artifact cũ tiếp tục chạy | Deploy chưa hoàn tất, cache hoặc nhầm slot/app | Xác nhận deployment record, hostname và build version |

### 22.1. Quy trình chẩn đoán từ ngoài vào trong

Khi không truy cập được Java API:

1. **Xác nhận URL/hostname**: đang gọi đúng app, region, slot và context path?
2. **Xác nhận Web App state**: tài nguyên Running và không có lỗi cấu hình?
3. **Xác nhận deployment**: artifact đúng version đã được triển khai chưa?
4. **Xác nhận runtime**: Java SE/JAR hay Tomcat/WAR, JDK có phù hợp?
5. **Xem startup logs**: JVM/Tomcat có chạy không, lỗi chính xác là gì?
6. **Xác nhận HTTP listener/port**: process có lắng nghe đúng interface/port?
7. **Thử health endpoint**: route trả 200 hay 404/5xx, context path có đúng?
8. **Kiểm tra dependency**: SQL, Storage, Key Vault, network/private DNS/identity?
9. **Kiểm tra sức chứa**: CPU/memory, instance recycle, threads, connection pool?
10. **Đối chiếu release**: lỗi bắt đầu sau deployment/config change nào, có thể rollback an toàn không?

Không “khắc phục” bằng cách tắt authentication hoặc mở public database firewall không giới hạn. Lấy thông báo lỗi và chẩn đoán đúng lớp.

### 22.2. Khi App Service startup thất bại

Một runbook thực tế nên ghi lại:

- Deployment ID, artifact version và commit.
- Runtime stack/OS và JDK version.
- Startup command và app settings thay đổi gần đây.
- Log exception chính xác (đã loại bỏ secret).
- Trạng thái health và thời điểm platform restart.
- Tình trạng dependencies.
- Quyết định rollback hoặc hotfix, người phê duyệt.
- Bằng chứng sau khắc phục.

## 23. Triển khai bằng CI/CD có kiểm soát

### 23.1. Một pipeline Maven tối thiểu

~~~text
Stage 1 — Validate
    - Checkout đúng Git commit
    - Build bằng JDK thống nhất
    - mvn test
    - Static checks / dependency scan

Stage 2 — Package
    - mvn package
    - Chọn artifact .jar hoặc .war theo runtime
    - Version/hash artifact

Stage 3 — Deploy staging
    - Xác thực tới Azure bằng identity được cấp quyền
    - Deploy đúng Web App/slot
    - Kiểm tra deployment result

Stage 4 — Smoke test
    - HTTPS /health
    - Một endpoint nghiệp vụ đọc
    - Kết nối dependency được kiểm soát
    - Kiểm tra logs và error rate

Stage 5 — Promote
    - Approval nếu cần
    - Slot swap / release mechanism được hỗ trợ
    - Theo dõi production và rollback khi cần
~~~

### 23.2. Nguyên tắc tái lập

- Build một lần, deploy **cùng artifact** qua các môi trường nếu có thể.
- Không rebuild với dependency version thay đổi giữa staging và production.
- Không chứa secret trong Git hoặc artifact.
- Ghi rõ runtime/JDK/Tomcat cho mỗi environment.
- Có phê duyệt cho production và kế hoạch rollback.
- Dùng health check của ứng dụng, không chỉ kết quả upload.
- Ghi rõ database migration là thay đổi riêng có rủi ro.

### 23.3. Khi không có staging slot

Ở Basic tier hoặc môi trường nhỏ, vẫn có thể tổ chức:

- Một Web App/plan staging **riêng** nếu được phê duyệt ngân sách.
- Artifact version và một quy trình smoke test độc lập.
- Thời gian maintenance window cho deployment nếu cần.
- Backup/configuration snapshot hoặc cách quay lại artifact cũ.
- Kiểm tra logs sau mỗi triển khai.

Không nên tuyên bố có zero-downtime deployment chỉ vì lệnh **az webapp deploy** hoàn tất.

## 24. Dọn dẹp tài nguyên lab an toàn

Khi kết thúc, hãy kiểm tra tài nguyên nào được tạo **riêng cho bài thực hành** và có dữ liệu/cấu hình cần giữ không:

1. Hai Web App Java SE/Tomcat có dữ liệu local hoặc deployment cần lưu không?
2. App Service Plan có đang phục vụ Web App khác không?
3. Resource group có Azure Monitor, Storage, Key Vault, database hoặc các tài nguyên khác của nhóm không?
4. Có public IP, custom domain, certificate, DNS hoặc integration dùng chung không?
5. Ai là owner và ai được phép xóa?
6. Có cần export logs, deployment metadata hoặc backup trước không?

Ví dụ có thể xóa **một Web App lab** sau khi kiểm tra kỹ:

~~~bash
az webapp delete \
  --resource-group "$RG" \
  --name "$JAVA_SE_APP"
~~~

**Xóa một Web App không tự bảo đảm phí của App Service Plan dừng**, nếu plan còn tồn tại. Chỉ xóa plan khi đã xác nhận không còn Web App/service khác sử dụng:

~~~bash
az appservice plan delete \
  --resource-group "$RG" \
  --name "$PLAN" \
  --yes
~~~

Các lệnh là ví dụ cho **lab do chính bạn sở hữu**, không phải hướng dẫn xóa môi trường dùng chung. Không tự xóa resource group production để tiết kiệm chi phí.

## 25. Checklist triển khai production

- [ ] Đã chọn rõ **Java SE executable JAR** hay **Tomcat WAR**.
- [ ] Artifact đã chạy/test local bằng JDK tương thích.
- [ ] Runtime stack/OS/Java/Tomcat còn được Azure hỗ trợ.
- [ ] Nếu là Tomcat, Servlet **javax/jakarta** khớp đúng phiên bản.
- [ ] Build artifact có version và dependency được kiểm soát.
- [ ] App Service Plan phù hợp region, SKU, CPU/memory, scale và ngân sách.
- [ ] Java process bind đúng interface/port; health endpoint kiểm tra readiness.
- [ ] App settings được quản lý theo môi trường, không chứa secret trong repo.
- [ ] Managed identity và quyền tối thiểu được cấp đúng scope.
- [ ] Network inbound/outbound, private DNS và database connectivity đã được thử.
- [ ] HTTPS/TLS, authentication/authorization và access restrictions được cấu hình.
- [ ] Logs, traces, metrics và alert đã bật trong phạm vi cần thiết.
- [ ] Có test cho lỗi khởi động, mất dependency và ứng dụng chạy nhiều instance.
- [ ] Không lưu business state duy nhất trên filesystem của Web App.
- [ ] Deployment vào staging hoặc môi trường kiểm thử trước production.
- [ ] Có kế hoạch rollback artifact và database migration tương thích.
- [ ] Đã xác nhận App Service Plan vẫn tính phí theo năng lực được cấp.
- [ ] Có runbook release, incident response, scaling và disaster recovery.

## 26. Bài tập thực hành

### Bài 1: Chọn runtime

Phân loại các ứng dụng sau theo **Java SE JAR**, **Tomcat WAR** hoặc cần đánh giá runtime khác:

1. Spring Boot REST API chạy embedded Tomcat và đóng gói executable JAR.
2. Java Servlet cũ dùng **javax.servlet** triển khai với Tomcat thế hệ cũ.
3. Ứng dụng Jakarta Servlet mới, build WAR cho Tomcat 10.1.
4. Ứng dụng Jakarta EE sử dụng các tính năng JBoss EAP đặc thù.
5. Chương trình Java chỉ đọc file rồi thoát sau 10 giây, không cung cấp HTTP.

Giải thích vì sao mục 5 không phù hợp mặc định với mô hình web hosting App Service.

### Bài 2: Deploy Java SE JAR

Trong một resource group lab được phê duyệt:

1. Build JAR mẫu và thử **java -jar** ở local.
2. Tạo App Service Plan Linux B1.
3. Liệt kê runtime và chọn Java SE tương thích JDK.
4. Tạo Web App và deploy JAR.
5. Gọi **/health** qua HTTPS.
6. Ghi lại build version, URL và logs.
7. Giải thích nguyên nhân khi JAR chạy local nhưng App Service trả 502/503.

### Bài 3: Deploy Tomcat WAR

Build Servlet WAR ở phần 7:

1. Xác nhận **jakarta.servlet** API tương thích Tomcat đã chọn.
2. Deploy WAR vào Web App Tomcat.
3. Tìm context path thực tế.
4. Kiểm tra **/health**.
5. Mô tả khác biệt với Java SE JAR về entry point và lifecycle.
6. Giải thích vì sao chỉ rename **.war** thành **.jar** không tạo executable app.

### Bài 4: Cấu hình database bảo mật

Orders API cần đọc Azure SQL Database qua mạng riêng và lấy secret từ Key Vault:

- Thiết kế VNet Integration và đường private access đến SQL.
- Cấu hình DNS và xác thực.
- Bật managed identity của Web App.
- Gán quyền Key Vault tối thiểu.
- Không lưu password/connection string trong repo.
- Lập health/smoke test an toàn và nêu rủi ro khi mở firewall quá rộng.

### Bài 5: Lập kế hoạch release production

Nhóm muốn nâng cấp Java runtime và WAR Tomcat vào cuối tuần:

1. Kiểm tra compatibility JDK/Servlet API và dependency.
2. Build một artifact có version.
3. Triển khai staging trên tier hỗ trợ hoặc môi trường riêng.
4. Kiểm tra health, logs, requests và database migration.
5. Swap/release theo quy trình được hỗ trợ.
6. Giám sát error rate/latency.
7. Trình bày kế hoạch rollback khi lỗi tương thích.

### Bài 6: Chi phí và vận hành

Một App Service Plan B1 chạy một JAR API và một WAR web app. Trong 12 giờ cuối tuần, hai ứng dụng không có request. Phân tích:

- Vì sao plan vẫn có thể phát sinh phí?
- Việc stop một app có ngừng phí compute của plan không?
- Những tài nguyên phụ trợ nào vẫn phát sinh phí?
- Khi nào có thể gom chung plan, khi nào nên tách?
- Nếu cần app chạy 24/7, tối ưu chi phí bằng cách nào mà không phá SLA?

### Câu hỏi tự kiểm tra

1. Java SE executable JAR và Tomcat WAR khác nhau như thế nào?
2. Vì sao một thư viện JAR bình thường không đủ để chạy Java web service?
3. **Main-Class** được dùng trong kiểu triển khai nào?
4. Vì sao Tomcat 9/10 có thể không tương thích khi đổi từ **javax** sang **jakarta**?
5. App Service Plan và Web App có cùng vai trò không?
6. Lệnh nào cho phép xem các runtime Linux hiện được Azure CLI hỗ trợ?
7. Deploy thành công có chứng minh API đã Healthy không?
8. Vì sao cần xác nhận context path sau khi deploy WAR?
9. VNet Integration có tự chặn public inbound access của Web App không?
10. Làm sao cấp quyền Key Vault mà không hard-code secret?
11. Vì sao không nên ghi file upload duy nhất vào filesystem của app instance?
12. Slot swap có tự rollback database schema không?
13. Dừng một Web App có làm phí App Service Plan bằng 0 không?
14. Khi scale out, vì sao session trong memory có thể trở thành vấn đề?

## 27. Tài liệu tham khảo

- [Azure App Service overview — Microsoft Learn](https://learn.microsoft.com/azure/app-service/overview)
- [Configure Java apps for Azure App Service](https://learn.microsoft.com/azure/app-service/configure-language-java)
- [Quickstart: Deploy a Java app to Azure App Service](https://learn.microsoft.com/azure/app-service/quickstart-java)
- [Azure CLI: az webapp deploy](https://learn.microsoft.com/cli/azure/webapp#az-webapp-deploy)
- [Java application deployment to Azure App Service](https://learn.microsoft.com/azure/developer/java/ee/how-to-deploy-to-azure-app-service)
- [Configure App Service application settings](https://learn.microsoft.com/azure/app-service/configure-common)
- [App Service deployment slots](https://learn.microsoft.com/azure/app-service/deploy-staging-slots)
- [App Service VNet integration](https://learn.microsoft.com/azure/app-service/overview-vnet-integration)
- [Use Key Vault references in App Service](https://learn.microsoft.com/azure/app-service/app-service-key-vault-references)
- [Monitor Azure App Service](https://learn.microsoft.com/azure/app-service/monitor-app-service)
- [Azure App Service pricing](https://azure.microsoft.com/pricing/details/app-service/)

