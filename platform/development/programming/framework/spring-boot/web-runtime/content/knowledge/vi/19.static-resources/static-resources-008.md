# Phân biệt tài nguyên trên classpath với tệp bên ngoài ứng dụng

## 1. Hai nguồn tài nguyên trông giống nhau nhưng có vòng đời khác nhau

Trong Spring Boot, một ứng dụng thường có cả **tài nguyên nằm trong classpath** lẫn **tệp trên hệ thống tệp bên ngoài ứng dụng**. Chúng đều có thể là HTML, CSS, JavaScript, ảnh, JSON, CSV hoặc các tệp văn bản, nhưng cách tìm, đóng gói, đọc, công bố qua HTTP và cập nhật rất khác nhau.

Ví dụ:
- **Classpath:** tệp **src/main/resources/static/logo.svg** được đưa vào artifact lúc build; khi chạy JAR, nó thường nằm ở đường dẫn logic **BOOT-INF/classes/static/logo.svg** bên trong JAR.
- **Bên ngoài:** tệp **/srv/myapp/public/logo.svg** được triển khai hoặc mount vào máy/container độc lập với JAR; đổi file này không đòi hỏi chỉnh lại byte của JAR.
- **Không phải cứ nằm trên classpath là public:** tệp **src/main/resources/private/messages.txt** có thể được ứng dụng đọc bằng ClassPathResource nhưng Spring Boot **không tự công bố nó thành HTTP URL**.
- **Không phải cứ là file bên ngoài thì có thể truy cập HTTP:** file bên ngoài chỉ được phục vụ nếu ứng dụng/proxy có một ánh xạ hoặc endpoint phù hợp và quyền truy cập cho phép.

Mục tiêu bài: chọn đúng vị trí lưu tệp theo mục đích; hiểu các tiền tố **classpath:** và **file:**; nắm quy tắc static content của Spring Boot; sử dụng Spring Resource để đọc an toàn khi đã đóng gói JAR; triển khai tệp bên ngoài đúng môi trường; và tránh lỗi quyền truy cập, đường dẫn, cache hoặc giữ dữ liệu cũ.

Phạm vi ví dụ chính: **Spring Boot 3.3.x, Java 17+, Spring MVC, executable JAR**. Spring WebFlux cũng có cơ chế static resources nhưng dùng cấu hình WebFluxConfigurer/WebFlux resource handler tương ứng; không bê nguyên cấu hình WebMvcConfigurer của Servlet sang WebFlux.

## 2. Bảng so sánh nhanh

| Tiêu chí | Tài nguyên classpath | Tệp bên ngoài ứng dụng |
| --- | --- | --- |
| Vị trí thường gặp lúc phát triển | src/main/resources/... hoặc tài nguyên từ dependency JAR | Thư mục do vận hành chọn, volume, ổ đĩa, thư mục tải lên |
| Khi đóng gói executable JAR | Thường được nhúng vào BOOT-INF/classes hoặc dependency JAR | Không tự được nhúng nếu không cấu hình build để đóng gói |
| Cách định danh trong Spring | classpath:static/app.css; ClassPathResource | file:/srv/myapp/public/app.css; FileSystemResource; Path |
| Tương ứng với java.io.File? | **Không bảo đảm**, đặc biệt trong JAR | Thường có đường dẫn vật lý trên filesystem |
| Thay đổi nội dung | Thường cần build artifact mới và triển khai lại | Có thể đổi bên ngoài; ứng dụng/cache phải đọc lại mới thấy thay đổi |
| Quyền ghi | Nên coi nội dung JAR/classpath đóng gói là chỉ đọc | Có thể đọc/ghi tùy quyền OS và chính sách ứng dụng |
| Phụ thuộc nơi khởi chạy | Chủ yếu phụ thuộc class loader và artifact | Đường dẫn tương đối phụ thuộc working directory; tuyệt đối phụ thuộc môi trường |
| Triển khai nhiều replica | Mỗi replica dùng cùng phiên bản artifact khi deploy đồng nhất | Cần mount/chia sẻ/đồng bộ dữ liệu theo thiết kế |
| HTTP public mặc định | Chỉ các vị trí static được framework cấu hình | Không public nếu không có resource mapping riêng |
| Phù hợp | Asset đi cùng phiên bản code: CSS, JS, icon, template, file mẫu | Asset cập nhật độc lập, file được vận hành quản lý, dữ liệu do người dùng tải lên |

**Nguyên tắc lựa chọn:** tài nguyên là một phần **phiên bản phần mềm** nên đóng gói; tài nguyên là **dữ liệu thay đổi theo môi trường hoặc sau triển khai** nên quản lý bên ngoài, thường qua một volume hoặc kho object storage. Quyết định còn phụ thuộc quyền truy cập, vòng đời dữ liệu và khả năng scale.

## 3. Classpath thực sự là gì?

**Classpath** là tập các vị trí mà class loader dùng để tìm class và resource khi chạy Java. Vị trí có thể là thư mục classes, JAR của ứng dụng hoặc JAR dependency. Classpath **không đồng nghĩa** thư mục làm việc hiện tại và không nhất thiết là một thư mục có thể duyệt bằng java.nio.file.Path.

Trong dự án Maven/Gradle chuẩn, file đặt dưới **src/main/resources/** được copy vào output resources/classes ở bước build. Khi package Spring Boot executable JAR, nội dung thường hiện dưới **BOOT-INF/classes/**. Ví dụ:

~~~text
src/main/resources/
├── static/
│   ├── index.html
│   └── css/site.css
├── private/
│   └── labels.txt
└── application.yml
~~~

Khi đóng gói, các resource này đi theo bản phát hành; startup dùng class loader của ứng dụng. Đường dẫn **src/main/resources/static/index.html** chỉ có ý nghĩa ở cây source. Trong JAR production, **không nên** mở tệp bằng:

~~~java
// SAI khi phụ thuộc cây mã nguồn còn tồn tại:
Files.readString(Path.of("src/main/resources/private/labels.txt"));
~~~

Lệnh trên có thể tình cờ thành công khi chạy tại thư mục dự án trên máy phát triển, nhưng sau khi deploy riêng file JAR, thư mục **src/main/resources** không còn. Một đường dẫn filesystem tương đối không tự trở thành đường dẫn classpath.

### 3.1. Cách đọc đúng tài nguyên nằm trong JAR

Sử dụng **ClassPathResource** hoặc **ResourceLoader**:

~~~java
Resource resource = new ClassPathResource("private/labels.txt");
try (InputStream stream = resource.getInputStream()) {
    String content = new String(
            stream.readAllBytes(), StandardCharsets.UTF_8
    );
    System.out.println(content);
}
~~~

Đây là **fragment**: cần import Resource, ClassPathResource, InputStream, StandardCharsets và xử lý IOException trong method; không phải chương trình độc lập. **getInputStream()** giúp đọc tài nguyên dù resource là mục trong JAR chưa giải nén ra filesystem. Đóng stream bằng try-with-resources.

Một mẫu tương đương khi có Spring ResourceLoader:

~~~java
Resource resource = resourceLoader.getResource(
        "classpath:private/labels.txt"
);
try (InputStream stream = resource.getInputStream()) {
    // Xử lý nội dung từng phần hoặc đọc toàn bộ nếu tệp nhỏ.
}
~~~

### 3.2. Vì sao resource.getFile() hay lỗi sau khi đóng gói?

**ClassPathResource.getFile()** chỉ hoạt động khi resource classpath được ánh xạ tới một file vật lý. Nếu file nằm **bên trong JAR**, thường không tồn tại một java.io.File riêng cho nó, nên getFile() có thể ném **FileNotFoundException** (hoặc IOException tương ứng ở đường gọi). Đây là lỗi phổ biến: code chạy được từ IDE vì output classes là thư mục thật, nhưng lỗi khi chạy bằng **java -jar**.

~~~java
// KHÔNG ỔN ĐỊNH khi tài nguyên nằm trong executable JAR:
File file = new ClassPathResource("private/labels.txt").getFile();
~~~

Thay bằng **getInputStream()**; với dữ liệu lớn, xử lý theo stream để không giữ toàn bộ trong RAM. Nếu thư viện bắt buộc nhận **Path/File**, có thể copy nội dung resource vào một file tạm có vòng đời/cleanup rõ ràng, nhưng nên tìm API InputStream trước. Không dựa vào việc giải nén toàn JAR để chữa lỗi.

**Lưu ý:** ClassPathResource.getURL() thường trả một URL truy cập được cho resource, kể cả JAR URL; điều đó không đồng nghĩa URL đó có thể ép thành filesystem path dùng với Path.of(...).

## 4. Tệp bên ngoài: Path, filesystem, mount và quyền truy cập

Một tệp **bên ngoài** được xác định bằng đường dẫn filesystem, ví dụ:

~~~text
Linux:   /srv/myapp/public/banner.txt
Windows: C:/apps/myapp/public/banner.txt
Local:   ./public-runtime/banner.txt
~~~

**Đường dẫn tuyệt đối** cho biết vị trí trên máy/container được chạy. **Đường dẫn tương đối** như **./public-runtime** thường được giải quyết theo **working directory (user.dir)** của tiến trình JVM, không phải theo thư mục chứa JAR và cũng không phải theo src/main/resources.

Ví dụ: cùng file application.jar, nhưng chạy từ hai thư mục khác nhau có thể khiến **./public-runtime/banner.txt** trỏ tới hai vị trí khác nhau. Vì thế trong môi trường deployment, nên truyền đường dẫn tuyệt đối qua environment/config hoặc mount volume vào đường dẫn ổn định.

Java NIO đọc file bên ngoài:

~~~java
Path path = Path.of("/srv/myapp/public/banner.txt");
String text = Files.readString(path, StandardCharsets.UTF_8);
~~~

Đây là fragment minh họa chạy trên hệ điều hành có đường dẫn đó; nếu file chưa có hoặc quyền bị từ chối, Files.readString ném IOException. Với tệp lớn, dùng Files.newInputStream hoặc API streaming.

### 4.1. Phân biệt tệp và nơi lưu trữ

- **File trên disk/container layer:** có thể biến mất khi container bị thay hoặc Pod bị xóa.
- **Persistent volume:** dữ liệu nằm ngoài vòng đời của process/container, nhưng vẫn phụ thuộc chính sách cấp phát/mount/chia sẻ.
- **Object storage (S3-compatible, GCS...):** là kho đối tượng truy cập qua API, **không mặc nhiên là một Path**. Không dùng FileSystemResource cho URL đối tượng như thể nó là local file.
- **Shared network filesystem:** cần xét latency, quyền, đồng bộ, lock, tính sẵn có và cache.

File bên ngoài có thể thay đổi tại runtime, nhưng **ứng dụng đã đọc và lưu trong RAM** sẽ không tự thấy nội dung mới nếu không reload; browser/proxy cache cũng có thể trả asset cũ.

## 5. Resource abstraction của Spring: đọc chung một interface, không xóa được khác biệt vật lý

**org.springframework.core.io.Resource** trừu tượng hóa cách truy cập tài nguyên. Những API quan trọng:

- **exists()**: cho biết resource có tồn tại tại thời điểm kiểm tra không; giữa exists() và lúc mở stream, file vẫn có thể bị xóa/thay đổi (race condition).
- **getInputStream()**: mở luồng đọc; caller chịu trách nhiệm đóng.
- **contentLength()**: trả kích thước nếu implementation hỗ trợ, nhưng có thể liên quan truy cập I/O.
- **lastModified()**: thông tin thời điểm sửa đổi khi có thể lấy được; không phải mọi resource đều hỗ trợ như nhau.
- **getFilename()**: tên logic của resource, không phải một Path tuyệt đối an toàn.
- **getFile()**: chỉ dùng nếu resource thực sự là tệp vật lý.
- **createRelative(...)**: giải quyết relative path theo implementation; không giả định quy tắc với mọi loại Resource giống nhau.

Các implementation thường gặp:

| Loại | Dùng cho | Điểm cần nhớ |
| --- | --- | --- |
| ClassPathResource | File trong classpath (có thể trong JAR) | Ưu tiên getInputStream(); getFile() không bảo đảm |
| FileSystemResource | File từ filesystem | Có Path/File, chịu ảnh hưởng quyền OS và filesystem |
| PathResource | Resource dựa trên java.nio.file.Path | Phù hợp với NIO, có thể dùng để ghi khi được phép |
| UrlResource | URL như file: hoặc https: | URL ngoài có thể cần network, timeout, bảo mật |
| ServletContextResource | Vị trí tương đối theo web application context | Không đồng nghĩa classpath; hành vi với WAR/JAR khác nhau |
| ByteArrayResource | Nội dung nằm trong byte[] | Thường tái đọc được; tốn RAM tương ứng |
| InputStreamResource | Stream đã mở sẵn | Thường chỉ đọc một lần, không giữ để tái đọc như descriptor thông thường |

**ResourceLoader** hiểu prefix tường minh:

~~~text
classpath:private/labels.txt
file:///srv/myapp/public/banner.txt
https://example.org/sample.txt
~~~

Không nên truyền một đường dẫn trần rồi đoán kết quả của Spring. Cách hiểu đường dẫn **không có prefix** có thể phụ thuộc loại ApplicationContext, API nhận tham số và cách resource được resolve. Với ý định rõ ràng, dùng **classpath:** hoặc **file:** hay khởi tạo ClassPathResource / FileSystemResource trực tiếp.

**classpath*:** thường dành cho cơ chế quét nhiều resource trùng pattern (ví dụ PathMatchingResourcePatternResolver). Nó không đồng nghĩa một resource đơn bình thường, và việc quét wildcard trong nhiều JAR có giới hạn theo class loader; chỉ dùng khi thật sự cần tổng hợp nhiều kết quả.

## 6. Spring Boot tự phục vụ tài nguyên tĩnh ở đâu?

Trong **Spring MVC**, Spring Boot mặc định tìm static content tại các vị trí classpath:

1. **classpath:/META-INF/resources/**
2. **classpath:/resources/**
3. **classpath:/static/**
4. **classpath:/public/**

Với ứng dụng Servlet, root của ServletContext cũng có thể là vị trí được phục vụ. Thứ tự chính xác khi resource trùng tên phụ thuộc cấu hình resource location và thiết lập ứng dụng; **tránh tạo nhiều file cùng URL path** ở các vị trí khác nhau.

Các ví dụ URL phổ biến với cấu hình mặc định:

| File được đóng gói | URL có thể truy cập |
| --- | --- |
| src/main/resources/static/index.html | GET / và GET /index.html trong trường hợp welcome page mặc định và không bị route khác ghi đè |
| src/main/resources/static/css/site.css | GET /css/site.css |
| src/main/resources/public/images/logo.svg | GET /images/logo.svg |
| src/main/resources/private/labels.txt | **Không tự tạo GET /private/labels.txt** |

Chú ý:
- **Classpath có resource** không có nghĩa **public HTTP resource**. Mặc định Boot chỉ map các vị trí static; file chứa bí mật/cấu hình không nên đưa vào vùng public.
- HTTP URL bỏ phần tiền tố thư mục static trong classpath. File ở **static/css/site.css** có URL **/css/site.css**, không phải **/static/css/site.css**.
- Đường dẫn **src/main/webapp** chủ yếu dành cho WAR/Servlet deployment; **không nên dùng nó** làm chỗ đặt static assets cho executable JAR.
- Trong WebFlux, Boot dùng resource handler tương ứng và thuộc tính thay đổi URL pattern là **spring.webflux.static-path-pattern**; ví dụ bài này dùng MVC với **spring.mvc.static-path-pattern**.

### 6.1. Khi thay đổi spring.web.resources.static-locations

Có thể cấu hình thay danh sách vị trí tìm resource tĩnh, ví dụ (minh họa trên Linux):

~~~yaml
spring:
  web:
    resources:
      static-locations:
        - "classpath:/static/"
        - "file:/srv/myapp/public/"
~~~

**Các vị trí khai báo thay thế danh sách mặc định**; nếu vẫn muốn asset ở classpath, phải liệt kê nó. Với directory location, cần dấu **/** cuối. Các path file: ở ví dụ trên gắn với hệ điều hành/container thực tế; thư mục phải tồn tại và quyền filesystem cho phép truy cập. Với cấu hình này, có thể cả hai nơi cùng ánh xạ vào URL gốc **/**, làm tăng nguy cơ trùng tên hoặc công bố nhầm file.

Với yêu cầu chỉ mở một thư mục external dưới prefix riêng, cân nhắc **WebMvcConfigurer.addResourceHandlers** để có URL rõ ràng như **/public-files/**. Không cần sửa toàn bộ static-locations trong trường hợp đó.

### 6.2. Chỉ đổi URL pattern không đổi vị trí lưu

~~~yaml
spring:
  mvc:
    static-path-pattern: "/assets/**"
~~~

Cấu hình trên đổi URL mapping mặc định của static resources thành **/assets/**, nhưng không tự di chuyển file từ classpath sang filesystem. **spring.mvc.static-path-pattern** (URL) và **spring.web.resources.static-locations** (nguồn file) là hai khái niệm khác nhau.

## 7. Ví dụ ứng dụng Java 17+ chạy được: hai nguồn, ba HTTP endpoint

Ví dụ Spring Boot 3.3.x + Spring MVC dưới đây chứng minh đồng thời:

1. File dưới **classpath:/static/** được phục vụ qua HTTP tự động.
2. File dưới **classpath:/private/** được Controller đọc bằng getInputStream(), nhưng không tự public.
3. File nằm ngoài JAR trong **./public-runtime/** được truy cập bằng Path và được công bố qua một **resource handler riêng**.

### 7.1. Cây dự án

~~~text
resource-origins/
├── pom.xml
├── public-runtime/
│   └── notice.txt
└── src/
    └── main/
        ├── java/com/example/resources/
        │   └── ResourceOriginsApplication.java
        └── resources/
            ├── application.yml
            ├── private/message.txt
            └── static/style.txt
~~~

**public-runtime/** nằm **ngoài src/main/resources** và ngoài artifact; thư mục/tệp này cần được tạo riêng trên môi trường deploy.

**pom.xml:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>resource-origins</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

**src/main/resources/application.yml:**

~~~yaml
server:
  port: 8080

demo:
  external-root: ./public-runtime
~~~

Cấu hình external-root là **đường dẫn tương đối** minh họa local. Trong production, nên override bằng một đường dẫn tuyệt đối/mount ổn định.

**src/main/resources/static/style.txt:**

~~~text
Bundled public v1
~~~

**src/main/resources/private/message.txt:**

~~~text
Bundled private v1
~~~

**public-runtime/notice.txt:**

~~~text
External public v1
~~~

### 7.2. Mã Java đầy đủ

**src/main/java/com/example/resources/ResourceOriginsApplication.java:**

~~~java
package com.example.resources;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class ResourceOriginsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResourceOriginsApplication.class, args);
    }
}

@Configuration
class ExternalStaticConfig implements WebMvcConfigurer {
    private final Path publicRoot;

    ExternalStaticConfig(@Value("${demo.external-root}") String root) {
        this.publicRoot = Path.of(root).toAbsolutePath().normalize();
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        String location = publicRoot.toUri().toString();
        if (!location.endsWith("/")) {
            location += "/";
        }
        registry.addResourceHandler("/public-files/**")
                .addResourceLocations(location);
    }
}

@RestController
class CompareResourcesController {
    private final Resource bundled = new ClassPathResource(
            "private/message.txt"
    );
    private final Path externalFile;

    CompareResourcesController(
            @Value("${demo.external-root}") String root
    ) {
        Path dir = Path.of(root).toAbsolutePath().normalize();
        this.externalFile = dir.resolve("notice.txt");
    }

    @GetMapping(
            path = "/api/compare",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    String compare() throws IOException {
        String bundledText;
        try (InputStream stream = bundled.getInputStream()) {
            bundledText = new String(
                    stream.readAllBytes(),
                    StandardCharsets.UTF_8
            ).strip();
        }

        String externalText = Files.readString(
                externalFile, StandardCharsets.UTF_8
        ).strip();

        return "classpath=" + bundledText
                + "\nfilesystem=" + externalText + "\n";
    }
}
~~~

Trong Java code trên:
- **ClassPathResource** đọc resource được đóng gói, không phụ thuộc việc file nằm ngoài hay trong JAR.
- **Path** và **Files.readString** truy cập resource bên ngoài; mỗi lần GET /api/compare đọc lại notice.txt. Đoạn demo dùng file nhỏ nên readAllBytes và readString hợp lý; với file lớn hãy stream.
- **WebMvcConfigurer** thêm ánh xạ **/public-files/** tới thư mục external, trong khi static handler mặc định của Boot vẫn phục vụ **/style.txt** từ classpath.
- **Path.toUri()** tạo URL **file:** phù hợp với OS, tránh tự nối tiền tố file:/ vào chuỗi đường dẫn kiểu Windows. Code bảo đảm directory location có dấu **/** cuối.
- Cấu hình không sử dụng user input để tạo path. Nếu mở rộng cho download động, không nối bừa path từ request; phải kiểm tra quyền và giới hạn file trong root được phép.

### 7.3. Biên dịch và chạy

Đặt đúng các file ở cây dự án, mở terminal tại thư mục **resource-origins/**.

~~~bash
mvn package
java -jar target/resource-origins-0.0.1-SNAPSHOT.jar
~~~

Yêu cầu có **JDK 17+**, Maven và cổng 8080 chưa bị tiến trình khác dùng. Nếu cổng bị chiếm, chọn cổng khác rồi thay URL kiểm tra tương ứng.

Từ terminal khác, gọi:

~~~bash
curl -s http://localhost:8080/style.txt
curl -s http://localhost:8080/public-files/notice.txt
curl -s http://localhost:8080/api/compare
~~~

Với dữ liệu mẫu và khi cả ba request thành công, **body** theo thứ tự là:

~~~text
Bundled public v1
~~~

~~~text
External public v1
~~~

~~~text
classpath=Bundled private v1
filesystem=External public v1
~~~

Các dòng trên là **body từng response**, không phải toàn bộ stdout của terminal hay HTTP headers. Dùng **curl.exe** trong PowerShell nếu alias curl của môi trường không hỗ trợ tham số như curl thật.

Thử thêm:

~~~bash
curl -i http://localhost:8080/private/message.txt
~~~

Kỳ vọng HTTP **404** với cấu hình mặc định của ứng dụng mẫu: file **private/message.txt** có trong classpath nhưng không ở thư mục static công bố. Endpoint **/api/compare** có thể đọc nội dung đó vì code **chủ động** đọc nó; điều này không làm resource tự có URL public.

### 7.4. Kiểm tra artifact bằng jar tf

Chạy:

~~~bash
jar tf target/resource-origins-0.0.1-SNAPSHOT.jar
~~~

Trong danh sách file của executable JAR sẽ có mục tương đương:

~~~text
BOOT-INF/classes/application.yml
BOOT-INF/classes/private/message.txt
BOOT-INF/classes/static/style.txt
~~~

**public-runtime/notice.txt** không có trong JAR vì nằm ngoài cây đóng gói ở ví dụ. File trong JAR có thể đọc bằng ClassPathResource.getInputStream(), nhưng không thể giả định **getFile()** trả file vật lý độc lập.

### 7.5. Thử thay đổi sau triển khai

**Lần thử A – file bên ngoài:** trong khi ứng dụng đang chạy, đổi nội dung **public-runtime/notice.txt** thành:

~~~text
External public v2
~~~

Gọi lại **GET /api/compare**. Vì code dùng Files.readString ở **mỗi request**, dòng **filesystem=External public v2** sẽ xuất hiện mà không cần build lại JAR (nếu ứng dụng đang đọc đúng directory). Tương tự, HTTP GET /public-files/notice.txt có thể thấy nội dung mới, nhưng tùy cache header, browser hoặc reverse proxy có thể còn lưu bản cũ; khi thử nên dùng curl hoặc bỏ cache phía client.

**Lần thử B – file classpath:** sửa **src/main/resources/static/style.txt** sau khi JAR đã được build, rồi gọi lại GET /style.txt trên tiến trình đang chạy bằng JAR cũ. Nội dung **không tự đổi** vì file đã được snapshot vào artifact. Cần **build JAR mới và chạy/triển khai phiên bản mới** để thay đổi bundled static asset. Nếu ứng dụng chạy từ classpath output trong IDE thì hành vi tài nguyên classpath có thể khác; bài thử phải chạy **java -jar** để phản ánh artifact production.

**Lần thử C – working directory:** chạy cùng JAR từ một working directory khác. Đường dẫn **./public-runtime** khi đó trỏ tới directory mới, vì thế /api/compare có thể lỗi khi notice.txt không tồn tại; /public-files/notice.txt có thể trả 404. Để chạy ổn định, override config bằng đường dẫn tuyệt đối:

~~~bash
java -jar target/resource-origins-0.0.1-SNAPSHOT.jar --demo.external-root=/srv/myapp/public
~~~

Đường dẫn **/srv/myapp/public** chỉ là ví dụ Linux; cần tạo directory, đặt notice.txt đúng chỗ và cấp quyền đọc. Khi chạy Windows, dùng đường dẫn tuyệt đối hợp lệ như **C:/apps/myapp/public**, đặt trong dấu nháy nếu có khoảng trắng.

## 8. Các cách cấu hình hay bị nhầm lẫn

### 8.1. File system location khác URL public

Với Spring:
- **classpath:static/style.txt** là đường dẫn nội bộ dùng để resolve resource; nó không phải URL HTTP.
- **file:///srv/myapp/public/style.txt** định danh một file trên host/container; nó cũng không tự trở thành URL HTTP.
- **GET /public-files/style.txt** là HTTP route chỉ hoạt động khi có handler hoặc proxy ánh xạ tới resource.

Phần **/public-files/** trong URL là tên do ứng dụng thiết kế; không nhất thiết giống tên thư mục vật lý.

### 8.2. application.yml đóng gói khác cấu hình ngoài

File **src/main/resources/application.yml** thường nằm trong classpath và chứa config mặc định của ứng dụng. Spring Boot có cơ chế nạp cấu hình từ nhiều nguồn, bao gồm file bên ngoài và environment variables, với quy tắc precedence riêng. Đó là **ConfigData configuration**; không đồng nghĩa với static file serving.

Ví dụ **spring.config.additional-location** có thể bổ sung nguồn config cho ứng dụng, nhưng **không** tự phục vụ những file cấu hình đó qua HTTP. Ngược lại, nếu cấu hình static-locations trỏ thẳng vào thư mục chứa secret hoặc config, có nguy cơ công bố dữ liệu ngoài ý muốn.

Phân biệt:
- **Cấu hình chạy:** ưu tiên config/environment/secret manager và quyền truy cập hẹp.
- **Static asset công khai:** chỉ đặt nội dung chủ động cho phép người dùng đọc.
- **Dữ liệu nghiệp vụ:** lưu ở DB/object storage/filesystem được bảo vệ và phục vụ qua API có kiểm soát khi cần.

### 8.3. Tài nguyên trong dependency JAR

Classpath có thể chứa file từ **dependency JAR**, không chỉ từ dự án chính. Khi nhiều JAR cùng chứa tên resource, class loader có thể chọn một tài nguyên theo thứ tự classpath; hành vi có thể khác giữa IDE và executable JAR. Tránh trùng path không cần thiết. Với trường hợp phải tìm nhiều resource, cân nhắc resource pattern resolver và kiểm thử trong artifact thật.

### 8.4. Không nhầm classpath resource với classpath* glob

Tiền tố **classpath:** thường tìm một resource theo tên. Tiền tố **classpath*:** thường được dùng bởi resolver có khả năng tìm nhiều resource theo pattern. Nó không biến file bên ngoài thành resource trên classpath; và wildcard trong JAR/loader đặc biệt có giới hạn. Không dùng glob để “liệt kê thư mục trong JAR” như liệt kê filesystem bình thường.

## 9. Bảo mật khi công bố thư mục tệp bên ngoài

Mở một directory qua HTTP có tác động trực tiếp: mọi file trong phạm vi mapping có thể truy cập nếu không có lớp bảo vệ thích hợp. Cần xem thư mục đó là **public directory**, không dùng để chứa secret hoặc dữ liệu nội bộ.

1. **Giới hạn root:** chỉ map thư mục dành riêng cho dữ liệu được phép public. Tránh các root rộng như **/**, **C:/**, thư mục home hoặc toàn bộ thư mục config.
2. **Không nối đường dẫn người dùng tùy ý:** ví dụ **Path.of(root, requestParam)** không bảo đảm an toàn khi người dùng đưa **../**, đường dẫn tuyệt đối hoặc các dạng mã hóa khác. Khi xây dựng API đọc file, resolve và normalize, kiểm tra path nằm trong root cho phép, xác thực/ủy quyền, giới hạn loại và kích thước; xét cả symlink và thay đổi file đồng thời.
3. **Quản lý symlink:** một thư mục public chứa symlink trỏ ra ngoài có thể làm lộ file tùy chính sách filesystem và resolver. Không coi kiểm tra chuỗi URL là kiểm tra phạm vi file sau khi resolve symlink.
4. **Quyền OS tối thiểu:** process web thường chỉ cần **read** với static public. Thư mục upload/write nên tách khỏi thư mục public; dùng user và mount có quyền đúng nhu cầu.
5. **Không public upload ngay khi nhận:** kiểm tra type thực tế, định dạng, kích thước, malware, tên file và quyền truy cập. Nếu phải serve upload cho user, nên dùng endpoint có authorization hoặc storage có signed URL, không map toàn bộ thư mục upload thành /**.
6. **Cache và headers:** quyết định Cache-Control, content type, Content-Disposition, X-Content-Type-Options và chính sách CSP phù hợp; tránh để nội dung do user kiểm soát được trình duyệt thực thi ngoài ý muốn.
7. **Không nhầm route với bảo vệ:** prefix **/private/** trong URL không làm file riêng tư. Bảo mật nằm ở quyền thực thi và kiểm soát access; nội dung trong **classpath:/static/private/** vẫn có thể public.

Trong ví dụ trên, /public-files/** chỉ dùng cho notice.txt và các asset được cho phép. Không đặt password, token, database dump, file .env hay bản sao config vào **public-runtime/**.

## 10. Cache, reload và cơ chế đóng gói

### 10.1. Resource mới không nhất thiết được client thấy ngay

Có ba nơi giữ dữ liệu cũ:
- **Build artifact:** resource classpath được đóng gói vào JAR; cần phiên bản artifact mới.
- **Ứng dụng:** ứng dụng có thể đọc file external lúc startup rồi lưu một bản vào singleton/cache; thay file ngoài không khiến object tự cập nhật.
- **HTTP cache:** browser, CDN hoặc proxy có thể dùng Cache-Control, ETag, Last-Modified và conditional requests; tài nguyên mới có thể chưa được tải do thời hạn cache.

Với asset classpath versioned như CSS/JS, chiến lược content hash trong URL giúp cache dài mà vẫn cập nhật khi deploy. Với external asset thay đổi tại cùng URL, cần phối hợp invalidation/revalidation hoặc URL versioning. Không đặt TTL rất dài cho file có nội dung thay thường xuyên mà vẫn dùng URL cố định.

### 10.2. File ngoài cần phát hành nguyên tử khi quan trọng

Nếu tệp lớn đang được ghi đè trong khi server phục vụ, client có thể đọc **nội dung dở dang**. Thực hành thường dùng: ghi file tạm trong cùng filesystem, xác minh nội dung, rồi rename/replace nguyên tử nếu nền tảng/filesystem cho phép; quản lý quyền và rollback. Với môi trường nhiều replica, mỗi replica có thể thấy file ở thời điểm khác nhau nếu không có cơ chế phân phối/đồng bộ.

### 10.3. Liên hệ với Docker/Kubernetes

Trong container, **file trong JAR hoặc image** thuộc bản release. Khi Pod/Container bị thay, dữ liệu ghi vào writable layer không nhất thiết còn. Đối với file bên ngoài có vòng đời dài:
- Dùng **volume/PVC** hoặc object storage theo nhu cầu.
- Đặt mount tại một đường dẫn tuyệt đối ổn định, ví dụ **/srv/myapp/public**.
- Truyền property qua environment/args để ứng dụng tìm đúng location.
- Không giả định mọi replica chia sẻ cùng filesystem.
- Phân quyền theo workload identity, user ID của container và chính sách storage.

Cách dùng external volume cho phép thay nội dung độc lập với JAR, nhưng đòi hỏi thiết kế nhất quán, backup, kiểm soát quyền và chiến lược cập nhật.

## 11. Tìm lỗi khi dev chạy được nhưng production hỏng

| Triệu chứng | Nguyên nhân hay gặp | Cách xác minh và sửa |
| --- | --- | --- |
| IDE đọc file được; chạy java -jar báo FileNotFoundException | Dùng ClassPathResource.getFile() trên resource trong JAR | Đọc bằng getInputStream(); kiểm tra jar tf |
| Chạy java -jar không tìm thấy src/main/resources/... | Dùng Path tới cây source code | Dùng classpath:... hoặc ClassPathResource |
| File static trả 404 sau deploy | Không được đóng gói, sai path, URL mapping khác hoặc ghi đè cấu hình static-locations | Dùng jar tf; đối chiếu URL, cấu hình và cổng đang chạy |
| File có trong classpath nhưng /file trả 404 | Không thuộc một vị trí static public mặc định | Đặt ở static/public nếu chủ động muốn public, hoặc tạo endpoint phù hợp |
| GET /public-files/... trả 404 | Đường dẫn external-root sai, thiếu file, thiếu dấu / ở resource location hoặc quyền không cho đọc | In/check absolute normalized root; kiểm tra tồn tại/quyền và working directory |
| API đọc file external trả 500 | File không tồn tại hoặc lỗi IOException/permission | Xem stack trace và quyền mount; trả lỗi có thông tin an toàn |
| Thay file bên ngoài mà browser vẫn hiện bản cũ | Cache browser/CDN/handler hoặc ứng dụng giữ bản cũ trong RAM | Kiểm tra HTTP cache headers, request không cache, app reload |
| Chạy trên Windows được, Linux lỗi | Path phân cách hoặc chữ hoa/thường khác, thư mục/mount khác | Dùng Path/URI đúng OS; quản lý path qua config |
| Đổi working directory làm ứng dụng mất file | Property dùng relative path | Truyền absolute path; kiểm tra user.dir |
| Lộ file cấu hình qua HTTP | Map nhầm thư mục chứa config/secret vào static-locations | Tách thư mục public, thu hẹp mapping, rotate secret bị lộ |
| Một replica trả bản cũ, replica khác trả bản mới | External files không được đồng bộ giữa replica | Quản lý storage/version phân phối và rollout |

Một quy trình chẩn đoán gọn:
1. Xác định **request URL** và resource **vật lý/logical** dự kiến.
2. Xác định resource là **classpath** hay **filesystem**, đừng đoán từ tên file.
3. Với classpath, kiểm tra output **jar tf**, class loader và cách code mở stream.
4. Với external, kiểm tra **absolute path** đã resolve, quyền filesystem, file size, working directory, volume mount và symlink.
5. Với HTTP, kiểm tra static handler/URL pattern, cổng web, security và cache headers.
6. Chạy lại bằng **artifact đóng gói** và cùng working directory/mount như production.

## 12. Câu hỏi tự đánh giá

**Câu 1.** File **src/main/resources/static/app.js** được build vào JAR. Trên production, chỉ sửa file trong source Git rồi gọi lại URL có thay đổi không?

**Trả lời:** Không nếu vẫn chạy JAR cũ. Phải build và deploy artifact chứa nội dung mới; cache HTTP cũng có thể cần invalidation hoặc versioned URL.

**Câu 2.** Vì sao **new ClassPathResource("private/a.txt").getInputStream()** thường hoạt động khi chạy java -jar, còn **getFile()** có thể lỗi?

**Trả lời:** Stream có thể đọc resource từ JAR/classloader, còn java.io.File yêu cầu file vật lý riêng trên filesystem.

**Câu 3.** Một file được mount tại **/srv/myapp/public/x.png**. Người dùng có tự gọi được **GET /x.png** không?

**Trả lời:** Không, chỉ vì file tồn tại không làm nó thành HTTP endpoint. Cần cấu hình static location/resource handler/proxy tương ứng và quyền đọc.

**Câu 4.** Cấu hình **spring.mvc.static-path-pattern=/assets/** có đưa file từ classpath sang directory bên ngoài không?

**Trả lời:** Không. Thuộc tính này đổi **URL pattern**; vị trí lấy resource do **spring.web.resources.static-locations** hoặc resource handler quyết định.

**Câu 5.** Một ứng dụng deploy bằng Docker chứa JAR và đọc **./public-runtime/notice.txt**. Khi container được restart ở working directory khác, điều gì xảy ra?

**Trả lời:** Đường dẫn tương đối resolve sang directory khác và có thể không tìm thấy file. Nên dùng đường dẫn tuyệt đối/mount ổn định, truyền qua cấu hình.

**Câu 6.** Nếu chuyển tệp upload vào thư mục public external, có cần xác thực khi truy cập nữa không?

**Trả lời:** Tùy yêu cầu bảo mật. Một mapping static công khai có thể bỏ qua kiểm tra quyền theo người dùng; với file riêng tư cần endpoint có authorization hoặc cơ chế storage được bảo vệ.

## 13. Kết luận và checklist áp dụng

**Tài nguyên classpath** gắn với class loader và phiên bản artifact; đọc qua Resource.getInputStream(), thường chỉ đọc và không bắt buộc có file thật trên filesystem. **Tệp bên ngoài** gắn với một Path/volume/kho lưu trữ có vòng đời riêng; có thể cập nhật không cần build lại JAR nhưng phải quản lý working directory, quyền, cache và tính nhất quán. **HTTP static resource** là một phép ánh xạ có chủ đích từ URL sang vị trí nguồn, không đồng nghĩa bất kỳ resource nào cũng public.

Trước khi triển khai, xác nhận:
- Asset có đi cùng phiên bản code hay cập nhật độc lập?
- Nó ở **classpath:/...** hay **file:/...**? Có kiểm tra bằng jar tf/absolute path?
- Code đọc bằng **getInputStream()** khi là classpath resource trong JAR?
- URL public có ánh xạ đúng? Có vô tình công bố thư mục chứa dữ liệu nhạy cảm?
- Đường dẫn external và mount có ổn định trên mọi replica?
- Cache, reload, quyền đọc/ghi và cơ chế triển khai phiên bản mới đã được xác định?
- Đã kiểm chứng bằng **java -jar** trên môi trường gần production, không chỉ chạy trong IDE?

## Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Servlet Web Applications, Static Content: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Framework — Resources (Resource, ClassPathResource, FileSystemResource, ResourceLoader): https://docs.spring.io/spring-framework/reference/core/resources.html
- Spring Framework — Spring MVC Static Resources: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html
- Spring Boot 3.3 — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
