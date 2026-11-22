# Phân biệt restart, tải lại tài nguyên và khởi động lại JVM trong Spring Boot Devtools

## 1. Tại sao ba thao tác này không giống nhau?

Khi phát triển một ứng dụng Spring Boot, bạn sửa Java, HTML, CSS hoặc file cấu hình và mong thấy kết quả mới. Có ít nhất **ba ranh giới cập nhật** khác nhau:

1. **Devtools restart (khởi động lại Spring application bằng restart classloader):** Spring Boot Devtools đóng application context đang chạy, bỏ classloader dành cho mã ứng dụng và khởi động lại phần application trong **cùng một JVM**. PID và mốc JVM start vẫn giữ nguyên.
2. **Resource reload / LiveReload (tải lại tài nguyên và giao diện):** các file static resource hoặc template mới được phục vụ mà **không phải tái tạo Spring application context**. LiveReload, nếu được cấu hình và trình duyệt hỗ trợ, có thể yêu cầu browser refresh để người dùng thấy nội dung mới.
3. **Full JVM restart (khởi động lại tiến trình JVM):** dừng process Java cũ, chạy lại một process Java mới. JVM, heap, classloaders, static state, startup flags, application context và các bean được tạo lại từ đầu.

Ba khái niệm này dễ bị gọi chung là “reload”, nhưng mức độ tác động khác nhau rõ rệt. Chọn sai có thể làm mất state đang debug, không nhận thay đổi mới hoặc tưởng một file HTML đổi mà cả server đã restart.

Bài thuộc nhóm **Devtools** của module Spring Boot Application Runtime. Sau bài này, bạn cần nhận biết chính xác loại cập nhật dựa vào **classpath**, **Spring context**, **JVM PID/start time**, **caching** và **cơ chế LiveReload**.

### Hình dung nhanh

~~~text
Mã Java đã biên dịch thay đổi
  -> Devtools phát hiện classpath đổi
  -> đóng context cũ / bỏ restart classloader cũ
  -> tạo restart classloader mới / khởi tạo context mới
  -> JVM PROCESS VẪN SỐNG

File static/template thay đổi trong classpath
  -> không cần restart Spring context
  -> server có thể phục vụ phiên bản tài nguyên mới
  -> LiveReload yêu cầu browser refresh (nếu có client)
  -> JVM VẪN SỐNG, CONTEXT VẪN LÀ CONTEXT CŨ

Dừng process Java rồi khởi chạy lại
  -> JVM cũ kết thúc
  -> JVM mới khởi động với flags/classpath/environment mới
  -> mọi classloader và context được tạo mới
  -> COLD START, PROCESS MỚI
~~~

**Kết luận quan trọng:** Devtools restart không phải một lần JVM restart; LiveReload cũng không phải Devtools restart. Và việc browser tự refresh không tự đồng nghĩa Java code đã được nạp lại.

## 2. Bảng so sánh ba ranh giới

| Tiêu chí | Devtools restart | Resource reload / LiveReload | Full JVM restart |
| --- | --- | --- | --- |
| Phạm vi tác động | Spring application + restart classloader | File tài nguyên / browser | Toàn bộ process Java |
| JVM PID | Giữ nguyên | Giữ nguyên | Thường khác, dù OS có thể tái sử dụng PID |
| JVM start time | Giữ nguyên | Giữ nguyên | Mới |
| Spring ApplicationContext | Thường tạo context mới | Giữ nguyên | Context mới trong process mới |
| Application singleton beans | Được tạo lại ở context mới | Không tạo lại chỉ vì reload resource | Được tạo lại |
| Static state của app trong restart classloader | Thường reset theo lần restart | Không đổi | Reset |
| Static state của thư viện trong base classloader | Có thể tồn tại | Không đổi | Reset |
| Classes Java ứng dụng sau biên dịch | Được nạp từ restart classloader mới | Không đổi | Được nạp trong JVM mới |
| Ứng dụng web có thể ngắt kết nối ngắn | Có | Thường không do reload resource | Có trong lúc process cũ/new chuyển tiếp |
| HTTP sessions | Phụ thuộc cấu hình/server; không coi là luôn mất | Thường không bị thay vì riêng resource | Phụ thuộc persistence bên ngoài và server |
| JVM flags như `-Xmx`, `-javaagent` | Không đổi | Không đổi | Có thể áp dụng flags mới |
| Thư viện JAR trong base classloader | Không nên kỳ vọng được thay mới | Không đổi | Nạp từ classpath mới |
| Cần biên dịch Java? | Có, để output classpath đổi | Không đối với HTML/CSS đã được copy tới runtime classpath | Thường cần nếu source mới |
| Cần browser refresh để thấy giao diện? | Có thể cần | Có; LiveReload client có thể làm tự động | Có thể cần |
| Mục tiêu | Vòng phản hồi nhanh cho thay đổi code/config | Chỉnh asset/template nhanh | Khởi động sạch, đổi JVM/dependencies |

Đây là bảng hành vi thông thường của Spring Boot 3.5 Devtools trong môi trường local khi chạy bằng IDE hoặc build plugin. Cơ chế bổ sung của framework, browser cache, multi-module hoặc container có thể khiến một số dòng khác đi; cần đo bằng dấu hiệu thực, không suy từ tên thao tác.

## 3. Spring Boot Devtools là gì?

`spring-boot-devtools` là dependency phục vụ **thời gian phát triển**. Nó cung cấp:
- Automatic Restart dựa trên thay đổi file trên classpath.
- LiveReload server để trình duyệt có client/extension tương thích tự refresh khi tài nguyên thay đổi.
- Các default thuận tiện khi phát triển, chẳng hạn giảm cache cho template engines và static resources.
- Một số cấu hình watcher, trigger file và phân tách classloader để vòng phát triển nhanh hơn.

Maven khai báo dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
~~~

Trong Gradle có thể khai báo ở configuration dành cho development:

~~~gradle
dependencies {
    developmentOnly("org.springframework.boot:spring-boot-devtools")
}
~~~

**Không dùng Devtools như một thành phần vận hành production.** Devtools tự vô hiệu hóa khi chạy ứng dụng đã được đóng gói đầy đủ trong ngữ cảnh thông thường, chẳng hạn `java -jar`. Các repackaged archives mặc định loại Devtools khỏi artifact. Không cố ép bật bằng system property trong production, vì remote development features và các development defaults có thể tạo nguy cơ bảo mật/vận hành.

### Chạy ở đâu thì Devtools có cơ hội hoạt động?

- **IDE/expanded classpath**: thường có `target/classes` hoặc `build/classes` là thư mục trên classpath; Devtools có thể watch.
- **`mvn spring-boot:run`** hoặc **`gradle bootRun`**: build plugin chạy application ở môi trường development; Devtools thường hoạt động nếu dependency có mặt và restart không bị tắt.
- **`java -jar target/app.jar`**: ứng dụng được đóng gói đầy đủ, Devtools thông thường **không hoạt động**; sửa source hoặc `target/classes` sau khi JAR đã khởi chạy cũng không tự thay class bên trong JAR.
- **Docker image production**: không nên dùng Devtools để hot deploy; thay image và rollout theo quy trình triển khai.

**Lưu ý về Maven/Gradle plugin:** chạy bằng build plugin cần giữ cơ chế fork phù hợp. Nếu cố tắt forking, môi trường và isolated application classloader mà Devtools mong đợi có thể không được tạo đúng; restart có thể hoạt động khác hoặc không hoạt động.

## 4. Cơ chế Devtools restart: hai classloader, một JVM

Automatic Restart của Devtools dùng **hai classloader**:

- **Base classloader**: giữ những lớp ít thay đổi, thường đến từ các JAR phụ thuộc bên ngoài.
- **Restart classloader**: giữ các lớp đang phát triển, thường từ thư mục output của dự án đang mở trong IDE.

Khi Devtools phát hiện một thay đổi hợp lệ:

~~~text
JVM được khởi động lúc T0, PID=P
  |
  +-- BaseClassLoader (thư viện ít thay đổi)
  |
  +-- RestartClassLoader #1 (compiled app classes)
  |       |
  |       +-- ApplicationContext #1
  |       +-- Các singleton #1
  |       +-- HTTP mappings / runners / web server...
  |
  +-- Classpath watcher phát hiện thay đổi
          |
          +-- Đóng ApplicationContext #1
          +-- Bỏ RestartClassLoader #1
          +-- Tạo RestartClassLoader #2
          +-- Chạy lại startup của ứng dụng
          |       |
          |       +-- ApplicationContext #2
          |       +-- Các singleton #2
          |       +-- HTTP mappings mới
          |
          +-- BaseClassLoader còn tồn tại
          +-- JVM vẫn PID=P, start time=T0
~~~

Đây là **restart ở cấp ứng dụng trong một JVM đang sống**, không phải cold start của JVM mới. Bởi vậy thường nhanh hơn chạy lại toàn tiến trình: các thư viện ở base classloader không cần nạp lại như lần đầu.

### Điều gì được tạo lại?

Thông thường các bean singleton, embedded web server, event listeners do context quản lý và application state nằm trong classloader bị thay sẽ được tạo lại ở application context mới.

Các mốc `@PostConstruct`, runner và Spring startup events có thể xuất hiện lại khi ứng dụng được khởi động lại. Các tài nguyên do bean cũ sở hữu cần được dừng/đóng trong đường close của context cũ, không được giả định Devtools chỉ “sửa bytecode trong JVM” mà giữ nguyên mọi object.

### Điều gì có thể còn sống?

- **JVM process** và các JVM-wide settings.
- Base classloader cùng các lớp thư viện ít thay đổi.
- Static variables hoặc caches do lớp **trong base classloader** giữ (không tự reset theo restart classloader).
- Thread hoặc resource **không được Spring quản lý đúng cách**, nếu code cũ rò chúng.
- Database, message broker, cloud resources ở ngoài JVM.
- Một số session state nếu servlet container/Devtools persistence configuration hỗ trợ.

Điều đó khiến một lỗi chỉ xuất hiện sau vài lần Devtools restart có thể là **rò tài nguyên hoặc classloader leak**, không phải “Java luôn reset mọi thứ” như với cold start.

### Restart có phải hot code swap?

Không. Devtools restart **thay application classloader và tạo lại context**. Nó khác với:
- Debugger `HotSwap` của IDE, vốn có thể thay bytecode một số class đang được nạp mà không restart toàn context, trong phạm vi JVM/debugger hỗ trợ.
- Các công cụ advanced class reloading như JRebel.
- Browser Hot Module Replacement (HMR) trong frontend build tool.

Vì thế đừng hứa Devtools giữ nguyên đối tượng Spring singleton hay mọi state in-memory sau khi đổi method Java.

## 5. Khi nào Devtools thực sự restart?

**Điều kiện quan trọng nhất: Devtools theo dõi file ở classpath, không theo dõi mọi file source một cách thần kỳ.**

Trong project Maven phổ biến:

~~~text
src/main/java/...       (Java source)
       |
       +-- mvn compile / IDE build
       v
target/classes/...      (compiled .class trên runtime classpath)
       |
       +-- Devtools FileSystemWatcher phát hiện classpath đổi
       v
Spring ApplicationContext restart
~~~

Đối với Eclipse/Spring Tools, hành động save có thể kéo theo tự động biên dịch. Với IntelliJ IDEA, thường cần **Build Project**, auto-build hoặc cấu hình tương đương khi application đang chạy. Chỉ sửa `src/main/java` nhưng IDE không compile/copy tới output thì **chưa có điều gì để Devtools nhận diện**.

Nếu dùng build plugin và cần cập nhật compiled classes:

~~~bash
mvn compile
~~~

Lệnh này chạy tại terminal khác khi app đang sống; nó cập nhật output nếu Java source thay đổi. Khi watcher thấy thay đổi classpath hợp lệ, restart có thể diễn ra sau khoảng polling và quiet period.

### Các bước thường bị bỏ qua

1. Save Java source.
2. IDE/Maven thực sự compile ra class file mới.
3. Class file được ghi vào thư mục runtime classpath mà process đang theo dõi.
4. Devtools watcher phát hiện update.
5. Devtools chờ giai đoạn ổn định để tránh restart giữa lúc compiler đang ghi nhiều file.
6. Context cũ đóng, context mới khởi động.

Nếu ứng dụng chạy một JAR đã đóng gói, việc compile ra `target/classes` không sửa các class bên trong **JAR process đang dùng**. Đây là lý do “đã build mà JAR vẫn chạy code cũ” không nhất thiết là bug của Devtools.

### Log Condition Evaluation Delta

Devtools có thể in **sự khác nhau** trong kết quả đánh giá auto-configuration khi restart, hữu ích nếu thêm/bớt bean hoặc đổi property conditional. Có thể tắt nếu log quá nhiều:

~~~properties
spring.devtools.restart.log-condition-evaluation-delta=false
~~~

Đây là diagnostic aid, không phải một lần restart riêng của JVM. Log delta cũng không thay thế exception root cause nếu lần startup mới thất bại.

## 6. Resource reload: static assets, templates và browser

Static resources như HTML, CSS, JavaScript, images, và view templates như Thymeleaf thường **không cần tái tạo Spring context** sau khi nội dung của chúng thay đổi.

Trong Spring Boot Devtools 3.5, các đường dẫn dưới đây được **loại trừ khỏi việc kích hoạt full application restart theo mặc định**:

~~~text
/META-INF/maven
/META-INF/resources
/resources
/static
/public
/templates
~~~

Điều này cho phép sửa trang hoặc template nhanh hơn. Tuy nhiên, file phải được cập nhật ở **đường dẫn resource thực sự đang được ứng dụng phục vụ**.

### Hai nghĩa của “reload”

**A. Resource được phục vụ với nội dung mới:** Browser hoặc HTTP client yêu cầu lại URL và server/templating engine trả về bản resource đã thay đổi. Spring context có thể giữ nguyên.

**B. LiveReload browser refresh:** Devtools cung cấp LiveReload server, còn browser cần client/extension có hỗ trợ LiveReload và kết nối tới server đó. Khi tài nguyên trên classpath đổi, Devtools gửi tín hiệu để browser tải lại giao diện.

**B không đồng nghĩa A.** Browser refresh chỉ là hành động yêu cầu trang lại. Nếu runtime resource vẫn là bản cũ do file chưa được copy, cache còn bật hoặc proxy/CDN còn giữ bản cũ, browser vẫn có thể thấy bản cũ.

### LiveReload có bắt buộc không?

Không. Bạn có thể:
- Mở trang trong browser và bấm refresh thủ công.
- Gọi `curl` để đọc lại static resource/template.
- Dùng LiveReload browser extension tương thích cho auto-refresh.

LiveReload **không phải** một cơ chế tự cập nhật Java classes trong JVM. Việc Java code đổi vẫn cần compile và thường cần Devtools restart.

### Thymeleaf và cache

Template engines thường có template caching để tối ưu production. Devtools áp dụng nhiều **development property defaults** nhằm giảm cache, trong đó có `spring.thymeleaf.cache=false` nếu dùng Thymeleaf. Vì thế một template đã được cập nhật trong runtime classpath thường có thể được đọc lại mà không restart context.

Nếu thấy template cũ, kiểm tra:
- File trong `target/classes/templates` hoặc output classpath thực tế đã cập nhật chưa?
- Cache template có bị override bật lại không?
- Response có đi qua proxy/cache khác không?
- Application đang chạy bằng IDE/plugin hay bằng packaged JAR?
- Bạn sửa đúng template mà view resolver đang dùng không?

### CSS/JS static resource

Devtools cũng điều chỉnh một số resource caching defaults cho phát triển. Nhưng browser có cache riêng. Khi có fingerprinted URLs, CDN, service worker hoặc reverse proxy, những tầng đó có thể làm bạn nhìn thấy asset cũ.

Để phân biệt, dùng HTTP client đọc nội dung thực:

~~~bash
curl -i http://localhost:8080/hello.txt
~~~

So sánh response body với file runtime classpath. Nếu `curl` thấy mới nhưng browser thấy cũ, nghi ngờ **browser cache hoặc service worker** trước khi nghi Devtools không restart.

## 7. Demo Java 17+ chạy được: đo JVM, context và tài nguyên

Mục tiêu demo: dùng **một ứng dụng** có 3 tín hiệu độc lập:

- `pid` và `jvmStartMillis`: nhận biết JVM process (PID có thể được OS tái sử dụng; start time mạnh hơn).
- `contextToken`: UUID tạo **một lần cho một ApplicationContext**, thay đổi khi Devtools restart context.
- `javaMessage`, static text và Thymeleaf view: so sánh lúc Java class đổi với lúc resource đổi.

Chạy demo trong môi trường development bằng `mvn spring-boot:run`; để quan sát full JVM restart, chủ động dừng process và chạy lại. Không chạy cùng lúc hai instance trên port 8080.

### 7.1. Cấu trúc project

~~~text
devtools-boundary-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/devtoolsboundary/
    │   └── DevtoolsBoundaryApplication.java
    └── resources/
        ├── application.properties
        ├── static/
        │   └── hello.txt
        └── templates/
            └── view.html
~~~

### 7.2. Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>devtools-boundary-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-devtools</artifactId>
            <optional>true</optional>
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

`spring-boot-starter-web` tạo embedded servlet server và hỗ trợ REST/static assets. `spring-boot-starter-thymeleaf` giải quyết template `view`. `spring-boot-devtools` phục vụ local development, được khai báo optional để tránh bị kéo transitively vào module khác.

### 7.3. Tệp Java hoàn chỉnh

Lưu vào `src/main/java/com/example/devtoolsboundary/DevtoolsBoundaryApplication.java`:

~~~java
package com.example.devtoolsboundary;

import java.lang.management.ManagementFactory;
import java.util.Map;
import java.util.UUID;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DevtoolsBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(DevtoolsBoundaryApplication.class, args);
    }

    @Bean
    ContextIdentity contextIdentity() {
        return new ContextIdentity(UUID.randomUUID().toString());
    }

    // Bean này chỉ có một instance trong mỗi ApplicationContext.
    record ContextIdentity(String token) {
    }

    @RestController
    static class DiagnosticController {
        private final ContextIdentity identity;

        DiagnosticController(ContextIdentity identity) {
            this.identity = identity;
        }

        @GetMapping("/diag")
        Map<String, Object> diagnostics() {
            return Map.of(
                    "pid", ProcessHandle.current().pid(),
                    "jvmStartMillis",
                    ManagementFactory.getRuntimeMXBean().getStartTime(),
                    "contextToken", identity.token(),
                    "appClassLoader",
                    String.valueOf(getClass().getClassLoader()),
                    "javaMessage", "java-v1"
            );
        }
    }

    @Controller
    static class ViewController {

        @GetMapping("/view")
        String view() {
            return "view";
        }
    }
}
~~~

Đây là một tệp Java độc lập trong Maven project trên, không có placeholder cần tự tạo thêm. Java 17 hỗ trợ `record`, `ProcessHandle`, `Map.of` và `UUID`. Spring Boot component scan nhận các controller static nested nằm trong package của lớp `@SpringBootApplication`.

**Giải thích năm field của GET /diag:**

| Field | Đọc từ đâu | Thay đổi khi nào |
| --- | --- | --- |
| `pid` | `ProcessHandle.current().pid()` | Thường khác khi chạy JVM process mới, nhưng PID có thể tái sử dụng |
| `jvmStartMillis` | `ManagementFactory.getRuntimeMXBean().getStartTime()` | Chỉ thay khi JVM thực sự bắt đầu lại |
| `contextToken` | UUID singleton bean của một context | Đổi khi context mới được tạo, kể cả Devtools restart |
| `appClassLoader` | Classloader tải DiagnosticsController | Thường xuất hiện restart classloader trong dev mode; representation không phải API nhận diện bền vững |
| `javaMessage` | Chuỗi hardcoded trong mã Java | Chỉ thành v2 sau khi class mới được nạp |

`Map.of` không cam kết thứ tự key trong JSON; các giá trị PID, timestamps, UUID và classloader string cũng không thể dự đoán chính xác. Vì thế **không có một literal stdout/JSON hoàn chỉnh cố định** cho endpoint này. Điều kiểm thử chính là **so sánh các field trước và sau thao tác**.

### 7.4. File application.properties

Tệp `src/main/resources/application.properties`:

~~~properties
spring.application.name=devtools-boundary-demo
server.port=8080
spring.main.banner-mode=off

# Giữ devtools restart và LiveReload ở mặc định khi chạy local.
spring.devtools.restart.enabled=true
spring.devtools.livereload.enabled=true
~~~

Bạn có thể bỏ hai property Devtools vì giá trị mặc định là enabled trong môi trường development đủ điều kiện. Không đặt `spring.devtools.restart.trigger-file` trong demo cơ bản, để mỗi thay đổi classpath hợp lệ được xem xét trực tiếp.

**Lưu ý:** `application.properties` cũng có thể là file classpath được watcher theo dõi; sửa cấu hình này có thể gây restart. Bài tập “resource reload không restart” ở dưới chỉ thay file trong `static` và `templates`.

### 7.5. File static hello.txt

Tệp `src/main/resources/static/hello.txt`:

~~~text
STATIC_VERSION=v1
~~~

Khi app đang chạy, thử:

~~~bash
curl -s http://localhost:8080/hello.txt
~~~

Response body kỳ vọng:

~~~text
STATIC_VERSION=v1
~~~

Dòng được trả về từ **resource**, không phải từ method Java trong DiagnosticsController. File `hello.txt` thay đổi không đòi biên dịch Java.

### 7.6. File Thymeleaf view.html

Tệp `src/main/resources/templates/view.html`:

~~~html
<!doctype html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Devtools Boundary Demo</title>
</head>
<body>
    <h1>TEMPLATE_VERSION=v1</h1>
    <p>Trang này được trả bởi Thymeleaf view resolver.</p>
    <p><a href="/hello.txt">Xem static resource</a></p>
    <p><a href="/diag">Xem runtime diagnostics</a></p>
</body>
</html>
~~~

`ViewController` trả view name `view`, còn Thymeleaf dùng prefix/suffix mặc định để tìm `classpath:/templates/view.html`. Đây là HTML hợp lệ; không nhất thiết phải có `th:text` để Thymeleaf render một file HTML.

Truy cập:

~~~bash
curl -s http://localhost:8080/view
~~~

Trong response HTML sẽ có chuỗi:

~~~text
TEMPLATE_VERSION=v1
~~~

Thứ tự markup có thể khác về whitespace nếu view engine xử lý, nhưng marker chữ là nội dung kiểm tra.

## 8. Thí nghiệm 1: baseline khi ứng dụng vừa chạy

Mở terminal A tại thư mục có pom.xml:

~~~bash
mvn spring-boot:run
~~~

Đợi server sẵn sàng trên `http://localhost:8080`. Trong terminal B, gọi:

~~~bash
curl -s http://localhost:8080/diag
curl -s http://localhost:8080/hello.txt
curl -s http://localhost:8080/view
~~~

**Kết quả có ý nghĩa:**

- `/diag` trả một PID `P1`, timestamp JVM `T1` và context token `C1`, kèm `javaMessage=java-v1`.
- `/hello.txt` trả `STATIC_VERSION=v1`.
- `/view` có `TEMPLATE_VERSION=v1`.
- ApplicationContext đã start thành công và có thể xem log startup tương ứng.

Ví dụ JSON **chỉ minh họa cấu trúc, không phải giá trị thật hay thứ tự key cố định**:

~~~json
{
  "pid": 11111,
  "jvmStartMillis": 1790000000000,
  "contextToken": "uuid-context-1",
  "appClassLoader": "org.springframework.boot.devtools.restart.classloader.RestartClassLoader@...",
  "javaMessage": "java-v1"
}
~~~

Đừng copy “11111” hay “uuid-context-1” làm expected value. Trong test thật, lưu **giá trị do endpoint trả** và so sánh các lần gọi.

## 9. Thí nghiệm 2: chỉ thay static resource/template, không restart context

Giữ terminal A đang chạy. Sửa hai file nguồn:

~~~text
src/main/resources/static/hello.txt:
  STATIC_VERSION=v2

src/main/resources/templates/view.html:
  <h1>TEMPLATE_VERSION=v2</h1>
~~~

Vì ứng dụng đang chạy trên **runtime classpath**, việc sửa source file có thể **chưa đủ** nếu IDE chưa copy resource tới output. Để thí nghiệm chỉ thay đúng hai resource mà không vô tình compile Java hoặc chạm application.properties, hãy copy riêng các file đã sửa:

**Bash/zsh, chạy trong terminal B tại project root:**

~~~bash
cp src/main/resources/static/hello.txt target/classes/static/hello.txt
cp src/main/resources/templates/view.html target/classes/templates/view.html
~~~

**Windows PowerShell (tương đương):**

~~~powershell
Copy-Item -LiteralPath .\src\main\resources\static\hello.txt -Destination .\target\classes\static\hello.txt -Force
Copy-Item -LiteralPath .\src\main\resources\templates\view.html -Destination .\target\classes\templates\view.html -Force
~~~

Các lệnh copy trên giả định Maven đã tạo `target/classes` và server đang chạy bằng `mvn spring-boot:run` như thí nghiệm. Nếu IDE/build tool dùng output directory khác, **hãy copy tới runtime classpath thực tế**, không rập khuôn đường dẫn.

Sau đó gọi lại:

~~~bash
curl -s http://localhost:8080/hello.txt
curl -s http://localhost:8080/view
curl -s http://localhost:8080/diag
~~~

**Kỳ vọng:**

- `/hello.txt` → `STATIC_VERSION=v2`.
- `/view` có `TEMPLATE_VERSION=v2`.
- `/diag` vẫn báo `javaMessage=java-v1`.
- `pid=P1`, `jvmStartMillis=T1` **không đổi**.
- `contextToken=C1` **không đổi**: không có bằng chứng context được tạo lại.
- Nếu browser có LiveReload client tương thích, browser có thể tự refresh; nếu không, bấm reload thủ công.

Đây là **resource reload**, không phải automatic application restart. Các đường dẫn `static/**` và `templates/**` được loại trừ khỏi restart trigger mặc định, dù thay đổi vẫn có thể được LiveReload phát hiện.

### Nếu browser vẫn hiển thị v1?

Đừng vội khởi động lại JVM. Xác minh theo thứ tự:

1. Có thật file đích trong `target/classes` đã chứa v2 không?
2. App có thực sự lấy resource ở classpath đó không?
3. `curl` đã thấy v2 chưa?
4. Thymeleaf cache có bị bật lại bởi property ưu tiên cao không?
5. Browser có hard cache, service worker, CDN hay reverse proxy không?
6. LiveReload extension/client có thực sự được bật và kết nối không?

Nếu `curl` đã thấy v2 mà trình duyệt vẫn cũ, vấn đề thường ở tầng browser/HTTP cache. Nếu `curl` cũng v1, kiểm tra resource path/copy/cache server trước.

## 10. Thí nghiệm 3: sửa Java rồi kích hoạt Devtools restart

Vẫn giữ ứng dụng đang chạy từ terminal A. Sửa literal trong `DiagnosticsController.diagnostics()`:

~~~java
"javaMessage", "java-v2"
~~~

Thay cho dòng cũ:

~~~java
"javaMessage", "java-v1"
~~~

Đây là **hai dòng thay thế trong code đã cho**, không phải hai dòng cần xuất hiện đồng thời trong Java file. Save source, sau đó compile khi terminal A đang hoạt động:

~~~bash
mvn compile
~~~

Devtools theo dõi classpath, nên thay đổi file class trong `target/classes` sẽ được phát hiện. Sau một khoảng ngắn để watcher nhận diện ổn định file, ứng dụng có thể log một vòng restart và phục vụ trở lại. **Không cần dừng JVM process cũ**.

Gọi lại:

~~~bash
curl -s http://localhost:8080/diag
curl -s http://localhost:8080/hello.txt
curl -s http://localhost:8080/view
~~~

**Kỳ vọng quan trọng:**

| Field/biểu hiện | Trước Java change | Sau Devtools restart |
| --- | --- | --- |
| `pid` | P1 | **P1** |
| `jvmStartMillis` | T1 | **T1** |
| `contextToken` | C1 | **C2** (UUID mới) |
| `javaMessage` | java-v1 | **java-v2** |
| `appClassLoader` | Loader của application lần đầu | Loader ứng dụng mới (toString thường khác) |
| `STATIC_VERSION` | v2 | v2 |
| `TEMPLATE_VERSION` | v2 | v2 |

`contextToken` gần như chắc chắn khác do một UUID mới từ bean factory method, nhưng UUID có xác suất trùng cực nhỏ về mặt toán học; đây là marker demo, không phải định danh transaction hay bảo đảm mật mã. `jvmStartMillis` và PID giữ nguyên là bằng chứng mạnh rằng **JVM không bị restart**.

Nếu `javaMessage` không đổi nhưng `contextToken` đổi, có thể Devtools restart bằng output Java cũ (compile sai module/đường output) hoặc đang gọi nhầm process/port. Nếu cả hai không đổi, kiểm tra compile, watcher, Devtools dependency và môi trường chạy.

**Cảnh báo:** trên đường Devtools restart, web server có thể dừng/khởi tạo lại ngắn; request giữa lúc này có thể fail. Devtools không phải rolling deployment hay hot swap zero-downtime cho production.

## 11. Thí nghiệm 4: dừng process và khởi động JVM mới

Để so sánh cold start, dừng ứng dụng chạy ở terminal A bằng cơ chế bình thường của terminal (ví dụ Ctrl+C cho `mvn spring-boot:run`), xác minh port 8080 không còn instance cũ, rồi chạy lại:

~~~bash
mvn spring-boot:run
~~~

Gọi:

~~~bash
curl -s http://localhost:8080/diag
~~~

Lúc này:
- `jvmStartMillis=T2` mới, khác `T1`.
- `pid` thường khác P1 (không dùng PID đơn độc như một bảo đảm, vì OS có thể tái sử dụng).
- `contextToken=C3` mới vì context tạo mới.
- `javaMessage=java-v2` vì source đã được compile ở thí nghiệm 3.
- Base classloader, restart classloader và JVM-wide static state đều được thiết lập lại từ đầu.

Đây là **full JVM restart**. Nếu trước đó bạn thay đổi JVM flags `-Xmx`, Java agent, JDK chạy thực hoặc environment variables tại process launcher, chỉ một **process mới** mới có thể nhận các cài đặt startup mới.

### Test bằng packaged JAR: ranh giới đặc biệt của Devtools

Sau khi dừng app phát triển, build:

~~~bash
mvn package
java -jar target/devtools-boundary-demo-0.0.1-SNAPSHOT.jar
~~~

Trong chế độ packaged JAR thông thường, **Devtools bị vô hiệu hóa và dependency thường bị loại khỏi JAR**. Đừng kỳ vọng sửa `src/main/java`, `target/classes` hoặc `src/main/resources` làm Java process `java -jar` tự Devtools restart.

Muốn đưa code/resources mới vào packaged JAR, cần build artifact mới rồi khởi chạy process mới (hoặc triển khai theo release workflow). Không được cố ép bật Devtools remote/restart trong image production để thay quy trình deployment.

## 12. Ba cách thay đổi và kết quả quan sát

| Thao tác | File ảnh hưởng | Phản hồi kỳ vọng |
| --- | --- | --- |
| Sửa Java + compile | `target/classes/**/*.class` | Devtools application restart trong cùng JVM |
| Sửa Java source nhưng chưa compile | `src/main/java` | Chưa chắc có thay đổi trong app đang chạy |
| Sửa `static/hello.txt` và copy tới classpath | `target/classes/static/hello.txt` | Resource reload, không restart context mặc định |
| Sửa `templates/view.html` và copy tới classpath | `target/classes/templates/view.html` | Template reload (khi cache phù hợp), không restart context mặc định |
| F5 / reload browser | Browser HTTP request | Tải lại trang, không đổi Java classes/context |
| LiveReload browser extension nhận event | Browser | Browser refresh tự động, không đồng nghĩa JVM restart |
| Đổi class library JAR ở base classloader | Dependency JAR | Thường cần full JVM restart để nạp dependency mới đúng |
| Đổi Maven/Gradle dependency graph | Build classpath | Build lại và restart JVM để đảm bảo toàn dependency graph mới |
| Đổi `-Xmx` hoặc `-javaagent` | JVM launch options | Full JVM restart bắt buộc |
| Đổi OS env var dùng lúc process start | Launch environment | Process mới để có environment mới |
| Sửa application.properties ở watched classpath | Classpath resource/config | Có thể kích hoạt Devtools restart (không phải chỉ LiveReload static) |
| Sửa một file ngoài classpath | Không được watch mặc định | Không tự có tác dụng trừ khi có cơ chế reload/extra paths cụ thể |
| Gọi `context.stop()` rồi `context.start()` | Lifecycle beans | Không tương đương Devtools restart hoặc JVM restart |
| Đóng một `ApplicationContext` | Context | Không tự tạo JVM mới, cũng không tự Devtools restart |

**Chú ý:** “thay dependency JAR thì luôn tự Devtools restart” là suy luận sai. Base classloader tồn tại qua các lần restart; cần **JVM mới** để có một classpath thư viện khác được nạp nhất quán.

## 13. Cấu hình kiểm soát restart và resource reload

### 13.1. Bỏ qua tài nguyên khi quyết định restart

Devtools mặc định không restart khi các resource phổ biến thay đổi. Nếu muốn **thay danh sách exclusion mặc định**:

~~~properties
spring.devtools.restart.exclude=static/**,public/**
~~~

Đây là ví dụ từ tài liệu chính thức. Nhưng việc **thay** exclusion list có thể khiến những đường dẫn vốn được loại khỏi restart trước đó (ví dụ `templates/**`) không còn bị loại; bạn có thể vô tình kích hoạt restart nhiều hơn.

Nếu muốn **giữ mặc định và chỉ thêm exclusion**:

~~~properties
spring.devtools.restart.additional-exclude=reports/**,docs/**
~~~

`additional-exclude` thường an toàn hơn khi chỉ muốn bỏ qua một vài path mới. Hãy đối chiếu với runtime classpath root, không tự ý đặt đường dẫn absolute source rồi cho rằng pattern chắc chắn match.

### 13.2. Theo dõi thêm đường dẫn ngoài classpath

~~~properties
spring.devtools.restart.additional-paths=../shared-resources
~~~

Ví dụ trên giả định một thư mục ngoài classpath cần watch. Đây là một **tùy chọn bổ sung vùng theo dõi**, không tự biến mọi file bên ngoài thành classpath resource hợp lệ hoặc khiến Java source được compile. Kết hợp exclusion khi muốn thay đổi dưới path đó chỉ dẫn đến LiveReload thay vì full restart.

### 13.3. Trigger file để tránh restart liên tục

Nếu IDE tự compile quá thường xuyên, có thể yêu cầu restart check chỉ được kích hoạt bởi một file đặc biệt:

~~~properties
spring.devtools.restart.trigger-file=.reloadtrigger
~~~

Tạo file này ở classpath resource, ví dụ:

~~~text
src/main/resources/.reloadtrigger
~~~

Sau khi sửa các file khác và compile/copy xong, thay đổi trigger file trong runtime classpath. Devtools sẽ kiểm tra các thay đổi đang chờ và chỉ restart nếu có nội dung cần xử lý. **Thay đổi trigger file không bảo đảm sẽ restart nếu không có thay đổi phù hợp nào khác**.

Trigger file phải là một **tên đơn giản không có đường dẫn** và file tương ứng xuất hiện trên classpath. Đây là cách nhóm phát triển điều khiển lúc nào Devtools kiểm tra restart, tránh restart nhiều lần trong một lượt IDE build.

### 13.4. FileSystemWatcher: poll interval và quiet period

Devtools dùng file system watcher có polling interval và quiet period để tránh đọc các file còn đang được compiler ghi. Nếu IDE tạo nhiều thay đổi và Devtools restart quá sớm, có thể tăng thời gian:

~~~properties
spring.devtools.restart.poll-interval=2s
spring.devtools.restart.quiet-period=1s
~~~

Các giá trị này làm chậm việc nhận diện đổi file để đổi lại sự ổn định trong workspace lớn hoặc trên file system có độ trễ. Không dùng chúng để “sửa” lỗi chưa copy classes vào đúng output: watcher không thể phát hiện một file chưa xuất hiện ở classpath.

### 13.5. Tắt LiveReload mà vẫn dùng restart

~~~properties
spring.devtools.livereload.enabled=false
~~~

Tắt LiveReload server, **không đồng nghĩa tắt Devtools application restart**. Bạn vẫn có thể sửa Java + compile để restart; chỉ là browser không tự được LiveReload yêu cầu refresh.

Lưu ý nhiều app Devtools cùng chạy: tài liệu nói chỉ một LiveReload server có thể được chạy cùng lúc trên môi trường đó. Nếu một ứng dụng khác đã chiếm server, app còn lại có thể không có LiveReload dù restart Java vẫn bình thường.

### 13.6. Tắt automatic restart

~~~properties
spring.devtools.restart.enabled=false
~~~

Trong `application.properties`, setting này ngăn file-watching restart. Nhưng Devtools có thể vẫn **khởi tạo restart classloader**. Đây là cách tắt việc quan sát thay đổi, **không phải cách đảm bảo hoàn toàn không có restart classloader**.

Muốn tắt hẳn hỗ trợ restart trước khi Spring Boot khởi động:

~~~java
public static void main(String[] args) {
    System.setProperty("spring.devtools.restart.enabled", "false");
    SpringApplication.run(MyApplication.class, args);
}
~~~

Đây là **đoạn minh họa không độc lập**: cần `MyApplication`, import và class ứng dụng. Điểm quan trọng là property phải được đặt **trước lời gọi SpringApplication.run**. Tốt hơn trong production là không đưa Devtools vào runtime classpath.

## 14. Khi nào bắt buộc phải khởi động JVM mới?

Một restart context trong cùng process **không tái tạo JVM**. Do đó các thay đổi sau thường đòi process mới:

- JVM startup options: `-Xms`, `-Xmx`, Java agents, module flags, native library paths.
- Chọn **JDK/JVM phiên bản khác**.
- Dependency JAR hoặc build classpath nền đã thay đổi, nhất là lớp được base classloader tải.
- Một global library/static cache ở base classloader cần reset thật.
- OS environment variables được đọc từ environment của **process** tại lúc launch.
- Native resources, state hoặc lỗi classloader leak chỉ được dọn dứt điểm khi process kết thúc.
- Chuyển artifact/container image đã build mới.
- Các thay đổi yêu cầu điều phối restart ở cluster/kết nối bên ngoài.

Một số config ứng dụng vẫn có thể áp dụng trong Devtools restart nếu chúng nằm trong classpath mới được load. Đừng đánh đồng **đổi YAML application property** với **đổi JVM launch flag**.

### Cold restart có phải luôn nhanh kém hơn Devtools?

Thường chậm hơn vì process JVM phải start và nạp base libraries lại, nhưng không có một số thời gian cố định. Với ứng dụng nhỏ, chênh lệch có thể ít; với ứng dụng lớn, classloader restart có thể tiết kiệm đáng kể thời gian.

Không dùng microbenchmark thiếu kiểm soát để khẳng định “Devtools nhanh gấp N lần” cho mọi app. Thời gian còn phụ thuộc database migrations, remote config, bean init, filesystem, IDE và network.

### Full JVM restart có luôn xóa sạch dữ liệu?

Nó xóa **heap/process state** cũ, nhưng không xóa dữ liệu lưu ngoài JVM:
- Database records.
- File disk, uploaded assets, persistent cache.
- Redis hoặc message queues.
- Session store bên ngoài.
- Cloud services và persistent volumes.

Nếu ứng dụng sau JVM restart vẫn có dữ liệu cũ, đó có thể là hành vi đúng do persistence, không phải Devtools không refresh.

## 15. Vòng đời và cleanup trong Devtools restart

Devtools restart phụ thuộc vào việc đóng context cũ. Nếu một resource do bean quản lý không được cleanup, mỗi lần restart có thể làm **rò thêm một instance**:

~~~text
Context #1 -> executor #1 khởi chạy
     |
     +-- Devtools restart -> Context #1 đóng
     |                       nhưng executor #1 không được shutdown
     |
Context #2 -> executor #2 khởi chạy
     |
     +-- Devtools restart -> Context #2 đóng
                             nhưng executor #2 không được shutdown

JVM vẫn sống:
  executor #1 + executor #2 + ...
~~~

Đó là một vấn đề nguy hiểm trong phát triển, và có thể gây port conflict, thread leak hoặc classloader leak.

### Ai chịu trách nhiệm đóng?

- Singleton `@Bean` sở hữu client/pool: dùng `@PreDestroy`, `DisposableBean` hoặc `@Bean(destroyMethod="close")` tùy contract.
- Worker background: dùng `SmartLifecycle.stop(Runnable)` với callback sau khi dừng thực sự hoàn tất.
- File stream hoặc response thuộc một request/task: đóng tại operation boundary.
- Executor tự tạo: owner phải gọi shutdown/awaitTermination theo policy.
- Resource bên ngoài JVM: cần lease, timeout hoặc recovery mechanism nếu process crash.

**Không** coi Devtools restart là “JVM mới nên mọi static/native resources chắc chắn reset”. Đó là điểm khác biệt lớn nhất với cold restart.

### Shutdown hook

Spring Boot 3.5 docs lưu ý Devtools dựa vào application context shutdown hook để đóng context trong quá trình restart. Nếu bạn tắt hook bằng `SpringApplication.setRegisterShutdownHook(false)`, Devtools restart có thể không hoạt động đúng.

Đừng tắt shutdown hook của context trong demo Devtools; nếu cần lifecycle đặc biệt cho ứng dụng production, hãy tách cấu hình development và production và hiểu đầy đủ hợp đồng cleanup.

### ApplicationRunner và startup events

Mỗi lần Devtools restart application context, pipeline Spring Boot startup có thể được gọi lại, bao gồm refresh và runners. Không đặt tác vụ nghiệp vụ **không idempotent** trong runner rồi giả định nó chỉ chạy một lần cho toàn bộ JVM.

Ví dụ: tự gửi email, tạo thanh toán, ghi message hoặc chạy migration destructive từ runner có thể bị lặp lại mỗi khi developer sửa class. Dùng profile, migration framework, idempotency guard hoặc tách job bên ngoài startup nếu cần.

## 16. Tình huống nhiều module và lỗi classloader

Trong multi-module project:
- Module đang mở trong IDE thường được load bằng restart classloader.
- JAR dependency thường vào base classloader.
- Một class có thể bị load sớm bằng reflection hoặc annotation scanning theo classloader khác với dự kiến.
- Cùng tên class nhưng do **hai classloader khác nhau** tạo thành **hai Class objects khác nhau**.
- Serialization với `ObjectInputStream` chuẩn có thể giải quyết class bằng loader không phù hợp.

Một số triệu chứng:
- `ClassCastException` dù tên type trông giống nhau.
- `NoClassDefFoundError` trong đường restart nhưng không xảy ra khi chạy JAR sạch.
- Reflection không thấy annotation/class cần thiết.
- Thay đổi module local không được phản ánh khi nó đang được đóng gói như JAR trong base classloader.
- App chỉ lỗi sau Devtools restart thứ hai hoặc thứ ba.

### Cách khoanh vùng

1. Tắt Devtools restart hoàn toàn trước `SpringApplication.run` và chạy lại ở môi trường development.
2. Nếu lỗi biến mất, nghi ngờ classloader phân tách chứ không chỉ code nghiệp vụ.
3. In classloader của các type liên quan:
   - `SomeType.class.getClassLoader()`.
   - `object.getClass().getClassLoader()`.
4. Kiểm tra module đang là output directory hay JAR.
5. Dùng cấu hình classloader của Devtools khi cần, không chỉ thêm bừa dependencies.

### File META-INF/spring-devtools.properties

Devtools hỗ trợ cấu hình các pattern `restart.include.*` và `restart.exclude.*` để chuyển classpath entries vào loader tương ứng.

Ví dụ **minh họa**, phải chỉnh regex theo đường dẫn classpath dự án thật:

~~~properties
restart.include.localmodule=/my-company-module-[\w\d.-]+\.jar
restart.exclude.largegenerated=/generated-library-[\w\d.-]+\.jar
~~~

Khác với `spring.devtools.restart.exclude` (loại resource khỏi **trigger restart**), file `META-INF/spring-devtools.properties` điều chỉnh **classloader assignment** của classpath entries. Hai khái niệm đều có từ “exclude” nhưng **không làm cùng một việc**.

Không sử dụng `System.properties` để thay thế file này; tài liệu mô tả nó là cấu hình trong `META-INF/spring-devtools.properties` ở classpath. Tên property key có suffix phải độc lập, và regex được áp dụng cho classpath entries, không phải cho Java source file cụ thể.

## 17. Troubleshooting: sửa file mà ứng dụng không đổi

| Triệu chứng | Lý do thường gặp | Kiểm tra và sửa |
| --- | --- | --- |
| Sửa Java nhưng `/diag` vẫn java-v1 | File .class chưa được compile/copy tới runtime classpath | IDE Build Project hoặc `mvn compile` |
| Compile rồi mà `contextToken` không đổi | Devtools không chạy hoặc watcher không thấy path | Dependency, IDE vs packaged JAR, classpath output, restart.enabled |
| Resource v2 trong source, HTTP vẫn v1 | Chưa copy vào runtime classpath | So file source và `target/classes` |
| Resource ở classpath đã v2, browser vẫn v1 | Browser/proxy/cache, view cache | Gọi curl, hard refresh, kiểm tra headers/caches |
| Browser không auto refresh | Không có LiveReload extension/client hoặc server disabled/port occupied | Cài/enable client nếu cần; refresh thủ công vẫn được |
| Tự refresh browser nhưng Java behavior vẫn cũ | LiveReload chỉ refresh trang | Compile Java để kích hoạt Devtools restart |
| Edit CSS làm cả context restart | Đã thay default `restart.exclude`, path ngoài exclusions hoặc build chạm class khác | Kiểm tra exclusions và file timestamps |
| Edit Java gây restart nhiều lần | IDE compile thành nhiều đợt, quiet period quá ngắn | Tăng quiet-period, poll-interval, dùng trigger file |
| Chạy `java -jar` mà chờ Devtools restart | Packaged application tắt Devtools | Dùng IDE/`mvn spring-boot:run` ở development |
| PID đổi sau sửa resource | Bạn thực sự đã restart process/container | Xem process manager/IDE autorestart |
| PID giữ nguyên nhưng contextToken đổi | Devtools/application context restart | Dựa vào jvmStartMillis và restart logs |
| contextToken đổi nhưng javaMessage không đổi | Classpath cũ hoặc build/module sai | Kiểm tra target/classes class file đúng |
| Sau restart bị Address already in use | Context cũ giữ socket hoặc process khác chiếm port | Kiểm tra destroy callbacks, port owner |
| Lỗi type cast chỉ trong dev mode | Base/restart classloader split | Kiểm tra classloader, thử tắt restart, include/exclude |
| Devtools bất ngờ không chạy khi dùng AspectJ weaving | Automatic restart không hỗ trợ mode này | Thay workflow/loại bỏ yêu cầu Devtools restart |
| Thay JVM -Xmx nhưng memory vẫn cũ | Devtools restart không tạo JVM mới | Dừng process và launch JVM với flag mới |
| Mỗi Devtools restart lại gửi một email | Runner hoặc @PostConstruct chứa side effect không idempotent | Tách tác vụ, dùng guard/profile/idempotency |
| “Rất nhiều log Condition Evaluation delta” | Devtools in chênh lệch auto-config khi restart | Cấu hình `log-condition-evaluation-delta=false` |
| Static change vẫn có app restart | IDE/build plugin cũng thay các class/resource khác | Xem timestamps và log watcher; copy riêng resource để test |
| Reload thành công nhưng session data vẫn còn | Session persistence hoặc external session store | Phân biệt app context, session và data persistence |

### Quy trình chẩn đoán tối thiểu

1. **Đọc cách launch:** IDE, `mvn spring-boot:run`, `bootRun` hay `java -jar`?
2. **Đọc PID và JVM start time:** Process có thực sự đổi không?
3. **Đọc context token/generation:** Spring context có được tái tạo không?
4. **Xác định file đã sửa:** Java .java, compiled .class, static asset, template hay pom/JVM arg?
5. **Đối chiếu runtime classpath:** File mới nằm đúng thư mục ứng dụng đang phục vụ chưa?
6. **Kiểm tra exclusion/trigger settings:** Có vô tình yêu cầu restart cho resource không?
7. **Kiểm tra caching nhiều tầng:** Template, static resource, browser, service worker, proxy.
8. **Đọc lifecycle cleanup logs:** Context cũ có close sạch không?
9. **Kiểm tra base/restart classloader:** Lỗi type/loading liên quan phân tách không?
10. **Thử cold JVM restart:** Nếu chỉ cold start mới đúng, khoanh vùng base classloader/process settings hoặc state rò.

## 18. Các phản ví dụ và khái niệm dễ nhầm

### 18.1. “Save file Java là Spring tự restart”

Không mặc định. Devtools cần **classpath output** thay đổi. Với IDE không auto-compile, save chỉ sửa source file; bytecode chưa đổi. Phải build/copy để watcher thấy class mới.

### 18.2. “LiveReload là hot swap Java”

Sai. LiveReload hướng tới **browser reload**. Java method không đổi chỉ vì browser gọi lại HTTP endpoint. Muốn Java code mới, cần class reload đặc biệt hoặc Devtools restart.

### 18.3. “Devtools restart bằng System.exit rồi chạy một JVM khác”

Sai. Điểm chính của Devtools là **JVM cũ còn sống**, base classloader tiếp tục tồn tại; restart classloader và context được thay. Cold JVM restart là quá trình ở tầng process launcher.

### 18.4. “Resource reload luôn giữ session của người dùng”

Không phải cam kết tổng quát. Trong resource-only reload, context không tái tạo; nhưng session vẫn phụ thuộc session timeout, store và server. Trong Devtools restart, Devtools có một số default hỗ trợ session persistence cho servlet, nhưng không nên suy ra mọi session/workload đều bất biến.

### 18.5. “Mọi static đều reset sau Devtools restart”

Sai. Static fields của lớp ở restart classloader thường được tái tạo, nhưng static fields trong base classloader có thể giữ nguyên. Chỉ cold JVM restart mới reset toàn bộ JVM process state, ngoài những dữ liệu lưu bền ngoài process.

### 18.6. “Tắt restart.enabled trong application.properties nghĩa là không có restart classloader”

Không hẳn. Tài liệu Spring Boot lưu ý property này có thể chỉ tắt watcher, trong khi classloader vẫn được khởi tạo. Muốn vô hiệu hóa hoàn toàn cần thiết lập system property trước `SpringApplication.run` hoặc loại Devtools.

### 18.7. “Thay resource gốc trong src là đủ để HTTP trả bản mới”

Không luôn đúng. Ứng dụng có thể phục vụ từ `target/classes` hoặc JAR, không trực tiếp từ `src/main/resources`. Hãy xác minh nơi runtime đang load resource.

### 18.8. “Thay dependency JAR được Devtools restart áp dụng tự động”

Không nên tin như vậy. Các JAR phụ thuộc thường ở base classloader; dependency/classpath mới có thể yêu cầu khởi động JVM mới.

### 18.9. “Đổi application.properties như CSS sẽ chỉ reload trình duyệt”

Không đúng trong trường hợp tổng quát. Configuration property có thể ảnh hưởng bean construction, web server hoặc auto-configuration. Thay file cấu hình trên classpath thường có thể kích hoạt Devtools restart; không xem như một static asset.

### 18.10. “Devtools restart zero downtime”

Không. Context/web server có thể đóng rồi khởi tạo lại. Devtools là công cụ development, không phải chiến lược rolling deploy hay hot upgrade không gián đoạn.

## 19. Bài tập tự thực hành

**Bài tập 1 — xác định ba danh tính:** Chạy demo, ghi lại `pid`, `jvmStartMillis`, `contextToken` từ `/diag`. Xác định field nào đo JVM process, field nào đo context.

**Bài tập 2 — static resource reload:** Sửa `hello.txt` từ v1 thành v2, chỉ copy file đó tới `target/classes/static`. Dùng curl kiểm chứng HTTP response v2 nhưng contextToken vẫn giống ban đầu.

**Bài tập 3 — template reload:** Sửa `view.html` từ v1 thành v2, copy đúng target/classes/templates. Kiểm tra `/view` đổi mà JVM timestamp/context token giữ nguyên.

**Bài tập 4 — LiveReload có/không client:** Mở browser, thử sửa static khi extension LiveReload được bật rồi tắt extension. Phân biệt browser auto-refresh với việc server phục vụ resource mới khi refresh thủ công.

**Bài tập 5 — Java restart:** Đổi `java-v1` sang `java-v2`, biên dịch bằng `mvn compile`. Kiểm tra contextToken đổi, JVM start time giữ nguyên.

**Bài tập 6 — cold restart:** Dừng process và chạy `mvn spring-boot:run` mới. Kiểm tra JVM start time đổi và token mới.

**Bài tập 7 — packaged JAR:** Build `mvn package`, chạy `java -jar`, sửa source rồi compile ở terminal khác. Xác minh packaged process không tự restart Devtools.

**Bài tập 8 — disable restart:** Đặt `spring.devtools.restart.enabled=false` trong application.properties, restart development process, sau đó sửa Java và compile. Giải thích vì sao watcher không kích hoạt context restart.

**Bài tập 9 — trigger file:** Thiết lập `.reloadtrigger`, sửa một class và compile nhưng chưa đụng trigger file. Sau đó cập nhật trigger file ở classpath, quan sát thời điểm restart.

**Bài tập 10 — classloader problem:** Tạo module phụ thuộc có một shared class; thử load nó từ thư mục project đang mở và từ JAR. So sánh classloader và điều chỉnh classloader include/exclude khi thật sự gặp lỗi.

**Bài tập 11 — resource leak:** Tạo một executor không được close khi context shutdown. Quan sát số thread qua vài lần Devtools restart trong môi trường test; sau đó thêm cleanup đúng và so sánh. Không để đoạn code leak này trong production.

**Bài tập 12 — property vs JVM flag:** Thay application property trên classpath rồi kích hoạt restart; so với thay `-Xmx` khi process vẫn sống. Giải thích vì sao thay JVM flag phải launch JVM mới.

## 20. Câu hỏi ôn tập

**Câu 1.** Devtools restart có tạo một JVM process mới không?

**Trả lời:** Không. Nó thay restart classloader và tái khởi tạo Spring application context trong JVM đang chạy.

**Câu 2.** Hai classloader của Devtools có vai trò gì?

**Trả lời:** Base classloader giữ thư viện ít thay đổi; restart classloader nạp mã ứng dụng đang phát triển. Restart thường chỉ thay restart classloader, tăng tốc vòng phản hồi.

**Câu 3.** Sửa `.java` rồi chỉ save có chắc tự restart không?

**Trả lời:** Không. Cần compiled classpath output thay đổi, qua IDE build/auto-compile hoặc `mvn compile`.

**Câu 4.** Sửa CSS/HTML được phục vụ mới có cần restart context không?

**Trả lời:** Thường không với static resources/templates được Devtools loại trừ restart, miễn runtime classpath/caching cho phép phục vụ nội dung mới.

**Câu 5.** LiveReload có tự sửa Java classes không?

**Trả lời:** Không. Nó gửi tín hiệu browser refresh khi resource đổi và client hỗ trợ; Java code cần workflow compile/restart riêng.

**Câu 6.** PID không đổi nhưng contextToken đổi cho biết điều gì?

**Trả lời:** Rất phù hợp với Devtools restart tạo context mới trong cùng JVM, đặc biệt khi `jvmStartMillis` cũng không đổi.

**Câu 7.** JVM start time đổi nhưng contextToken cũng đổi cho biết điều gì?

**Trả lời:** Phù hợp với full JVM restart. Context mới là hệ quả của process mới.

**Câu 8.** Tại sao `java -jar` không có Devtools auto restart mặc dù pom chứa dependency?

**Trả lời:** Packaged application thông thường vô hiệu hóa Devtools và repackaged archives mặc định loại Devtools khỏi artifact.

**Câu 9.** Khi nào cần khởi động JVM mới?

**Trả lời:** Khi thay JVM flags/JDK, classpath nền/dependency JAR, startup OS environment hoặc muốn reset toàn process state.

**Câu 10.** `spring.devtools.restart.exclude` khác `additional-exclude` thế nào?

**Trả lời:** `exclude` thay danh sách exclusion; `additional-exclude` giữ exclusions mặc định và bổ sung pattern.

**Câu 11.** `META-INF/spring-devtools.properties` khác `spring.devtools.restart.exclude` thế nào?

**Trả lời:** File META-INF với `restart.include/exclude.*` chọn classpath entry đi vào base/restart classloader; property `spring.devtools.restart.exclude` kiểm soát resource changes có kích hoạt restart không.

**Câu 12.** Vì sao app chỉ lỗi sau Devtools restart?

**Trả lời:** Có thể rò thread/resource, static state trong base classloader, hoặc classloader compatibility/reflection/serialization issue. Cần so sánh với cold start và kiểm tra cleanup.

**Câu 13.** Nếu template v2 đã ở target/classes nhưng browser vẫn thấy v1?

**Trả lời:** Kiểm tra template cache, browser/proxy/service-worker cache, đúng template path và HTTP response qua curl.

**Câu 14.** Devtools restart có bảo đảm session trong browser bị xóa?

**Trả lời:** Không. Một số cấu hình/devtools defaults hỗ trợ session persistence; cần kiểm tra session storage thực tế.

**Câu 15.** Có nên dùng Devtools để cập nhật nóng một ứng dụng production?

**Trả lời:** Không. Devtools là developer tool; production nên dùng build/deploy/rollout và graceful shutdown theo quy trình bảo mật/vận hành.

## 21. Tài liệu chính thức và tổng kết

Tài liệu đối chiếu theo nhánh Spring Boot 3.5.16:

- [Spring Boot 3.5 — Developer Tools](https://docs.spring.io/spring-boot/3.5/reference/using/devtools.html): module Devtools, automatic restart, restart vs reload, resources, LiveReload, trigger file, classloader và limitations.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): các property `spring.devtools.restart.*`, caching và LiveReload.
- [Spring Boot 3.5 — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html): repackaging và phát hành JAR.
- [Spring Boot 3.5 — Web Servlet / Static Resources](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): static content, templates và đường phục vụ tài nguyên.
- [Java 17 — ProcessHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessHandle.html): định danh process khi quan sát JVM.
- [Java 17 — RuntimeMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/RuntimeMXBean.html): `getStartTime()` và thông tin runtime JVM.

### Ghi nhớ

1. **Devtools restart**: thay restart classloader và application context trong **cùng JVM**.
2. **Resource reload**: static asset/template được phục vụ lại mà **không nhất thiết tái tạo context**.
3. **LiveReload**: browser tự refresh khi có client hỗ trợ; không phải Java hot swap.
4. **Full JVM restart**: process Java mới, heap/base classloader/start flags được nạp từ đầu.
5. Devtools **watch runtime classpath**, không tự đọc mọi thay đổi ở `src/main/java` nếu chưa compile.
6. Static/templates thường được **exclude khỏi restart**; cần đúng runtime classpath và cache policy.
7. So sánh `pid + jvmStartMillis + contextToken` để xác nhận ranh giới thật.
8. Packaged `java -jar` thông thường **không kích hoạt Devtools**; đừng dùng Devtools trong production.
9. Khi thay dependency JAR, JDK, `-Xmx` hoặc OS environment của process, hãy dùng **JVM mới**.
10. Cleanup lifecycle cần đúng dù Devtools restart: JVM không tự reset mọi resource tồn tại trong base classloader.
