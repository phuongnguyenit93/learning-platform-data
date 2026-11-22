# Thư mục static, public, resources và META-INF/resources trên classpath

## 1. Mục tiêu và phạm vi

**Tài nguyên tĩnh (static resources)** là tệp có sẵn, thường được trả nguyên nội dung thay vì dựng động cho từng request: HTML, CSS, JavaScript, hình ảnh, SVG, font, tài liệu văn bản... Trong một ứng dụng **Spring Boot Web MVC** sử dụng cấu hình mặc định, bạn có thể đặt những tệp này ở bốn vị trí trên **classpath**:

1. `classpath:/static/`
2. `classpath:/public/`
3. `classpath:/resources/`
4. `classpath:/META-INF/resources/`

Bốn vị trí là **nguồn tìm tệp**, không phải bốn tiền tố URL bắt buộc. Theo mặc định, Spring MVC ánh xạ tài nguyên tĩnh vào URL pattern `/**`; tên `static`, `public`, `resources` hoặc `META-INF/resources` thường **không xuất hiện** trong URL trả về cho trình duyệt.

Sau bài này, bạn có thể:

- Giải thích `classpath` trong một ứng dụng Java/Spring Boot và vị trí thật của bốn thư mục trong cấu trúc nguồn.
- Ánh xạ đúng đường dẫn tệp thành URL cho request HTTP.
- Chạy một ứng dụng Spring Boot có tài nguyên ở cả bốn nơi và kiểm tra khi chạy bằng Maven hay executable JAR.
- Phân biệt tài nguyên tĩnh với `templates`, `application.properties`, API controller và thư mục `src/main/webapp`.
- Hiểu tác động của `spring.mvc.static-path-pattern`, `spring.web.resources.static-locations`, bảo mật và tài nguyên trùng tên.
- Chẩn đoán các trường hợp nhận 404, 401/403, file cũ do cache hoặc không thấy asset sau khi đóng gói.

Các ví dụ chính dùng **Spring Boot 3.3.x, Java 17+, Spring MVC, embedded Tomcat, Maven**. Với WebFlux, bốn nguồn classpath tương tự nhưng handler và thuộc tính ánh xạ URL có khác biệt (mục 10).

## 2. Classpath là gì, và vì sao có hai chữ resources?

**Classpath** là tập hợp các thư mục và JAR mà Java class loader có thể tìm class và resource khi chạy chương trình. Trong cấu trúc dự án Maven thông dụng:

~~~text
assets-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/                          <- mã nguồn Java
        │   └── com/example/assetsdemo/
        │       └── AssetsDemoApplication.java
        └── resources/                     <- gốc tài nguyên nguồn
            ├── application.properties
            ├── static/                    <- classpath:/static/
            ├── public/                    <- classpath:/public/
            ├── resources/                 <- classpath:/resources/
            └── META-INF/
                └── resources/             <- classpath:/META-INF/resources/
~~~

**Hai thành phần tên `resources` có ý nghĩa khác nhau:**

- `src/main/resources/` (thư mục **bên ngoài**): thư mục nguồn tiêu chuẩn mà Maven/Gradle đưa tài nguyên vào classpath. Nó không tự là một URL public.
- `src/main/resources/resources/` (thư mục **bên trong**): một trong bốn nguồn mặc định được Spring Boot tìm khi có request tài nguyên tĩnh. Cái tên lặp lại là hợp lệ và cần thiết để tệp nằm đúng `classpath:/resources/`.

Ví dụ:

~~~text
Tệp trong mã nguồn:
  src/main/resources/resources/docs/guide.txt
Sau khi được đưa vào classpath:
  resources/docs/guide.txt
Nguồn tìm mặc định của Spring MVC:
  classpath:/resources/
URL mặc định:
  GET /docs/guide.txt
~~~

Tệp `src/main/resources/application.properties` nằm trực tiếp ở **gốc classpath**, nhưng **không được Spring MVC công bố như static asset** chỉ vì nó thuộc classpath. Đây là ranh giới quan trọng giữa “được ứng dụng đọc” và “được phép phục vụ qua HTTP”.

Trong một bản build Maven thông thường, nội dung `src/main/resources` được sao chép vào `target/classes`; trong Gradle, nội dung tương ứng thường nằm ở `build/resources/main`. Khi đóng gói Spring Boot executable JAR, tài nguyên ứng dụng thường ở `BOOT-INF/classes/`. Đường dẫn vật lý thay đổi theo cách build, còn đường dẫn **tương đối với classpath** vẫn là khái niệm chủ đạo.

## 3. Bốn thư mục mặc định khác nhau thế nào?

| Nguồn trên classpath | Vị trí Maven đặt tệp | Ý nghĩa sử dụng phổ biến | URL ví dụ |
| --- | --- | --- | --- |
| `classpath:/static/` | `src/main/resources/static/` | CSS, JS, ảnh, trang HTML tĩnh của ứng dụng | `/css/site.css` |
| `classpath:/public/` | `src/main/resources/public/` | File công khai khác, phân nhóm theo cách tổ chức dự án | `/about.html` |
| `classpath:/resources/` | `src/main/resources/resources/` | Một nguồn tài nguyên tĩnh bổ sung; dễ nhầm với thư mục nguồn bên ngoài | `/docs/guide.txt` |
| `classpath:/META-INF/resources/` | `src/main/resources/META-INF/resources/` | Asset theo quy ước Servlet và tài nguyên được đóng gói trong dependency JAR | `/icons/logo.svg` |

**Cả bốn thư mục đều có thể phục vụ cùng loại tệp** nếu không có ràng buộc khác. Không có quy tắc rằng `static` chỉ cho CSS, `public` chỉ cho HTML hoặc `META-INF/resources` chỉ cho thư viện. Mục đích phân nhóm trong bảng mang tính tổ chức dự án, không phải giới hạn của Spring.

Với cấu hình mặc định, ví dụ:

~~~text
src/main/resources/static/css/site.css
                    └── css/site.css  -->  GET /css/site.css

src/main/resources/public/about.html
                    └── about.html    -->  GET /about.html

src/main/resources/resources/docs/guide.txt
                    └── docs/guide.txt --> GET /docs/guide.txt

src/main/resources/META-INF/resources/icons/logo.svg
                    └── icons/logo.svg --> GET /icons/logo.svg
~~~

Đặc biệt, `/static/css/site.css` **không** phải URL mặc định của tệp `static/css/site.css`. URL mặc định là `/css/site.css` vì Spring lấy đường dẫn **sau thư mục gốc tìm kiếm**.

Nếu có nhiều tệp ở các gốc khác nhau cùng tạo ra **một URL**, ví dụ `static/logo.svg` và `public/logo.svg`, bạn đã tạo xung đột tên. Kết quả phụ thuộc vào thứ tự tìm nguồn/cấu hình/classpath; không nên dựa vào “thư mục nào được ưu tiên” để tổ chức bài học hoặc ứng dụng. Hãy đặt đường dẫn tương đối riêng biệt và kiểm tra JAR cuối cùng.

### 3.1. Vì sao có META-INF/resources?

`META-INF/resources` là một quy ước liên quan đến việc cung cấp nội dung web từ JAR trên classpath. Nhờ đó, **thư viện phụ thuộc** có thể phân phối asset của chính nó trong JAR thay vì yêu cầu ứng dụng sao chép thủ công.

Ví dụ, một dependency dạng WebJar có thể chứa file dưới `META-INF/resources/webjars/...`. Spring Boot có cơ chế phục vụ WebJars thông qua đường dẫn `/webjars/**` theo quy ước đóng gói và cấu hình liên quan. Việc đặt một file vào `META-INF/resources` trong **ứng dụng của bạn** cũng hoàn toàn hợp lệ.

Đừng nhầm `META-INF/resources` với thư mục `META-INF` bất kỳ trong JAR. Không phải mọi file dưới `META-INF` đều trở thành tài nguyên web. Chỉ những vị trí được resource handler cấu hình làm nguồn tìm kiếm mới có ý nghĩa với URL HTTP.

## 4. Request tài nguyên được xử lý thế nào?

Trong Spring MVC (cấu hình Spring Boot mặc định), `ResourceHttpRequestHandler` phục vụ tài nguyên tĩnh. Hình dung quy trình:

~~~text
GET /css/site.css
        |
        v
DispatcherServlet
        |
        | Mapping của controller/route nếu khớp
        | Nếu không có handler phù hợp ở mức ưu tiên cao hơn
        v
Static resource handler (mặc định /**)
        |
        | Tìm "css/site.css" trong các static locations
        v
classpath:/static/css/site.css
        |
        v
Đọc tài nguyên, xác định kiểu nội dung phù hợp
        |
        v
HTTP response: 200 OK, Content-Type phù hợp, nội dung CSS
~~~

Các điểm cần hiểu:

- Đối với file tĩnh thông thường, **không cần viết `@RestController` hoặc `@GetMapping`** để trả từng tệp; resource handler tự làm.
- Đường dẫn `/**` là pattern fallback rộng cho static asset. Nó không đảm bảo mọi URL đều có file: nếu không tìm thấy tệp, request vẫn có thể nhận **404**.
- Route thật của controller/router thường được xét trước fallback welcome/static handler. Vì thế có controller trả `/`, trang `index.html` chưa chắc là nội dung được chọn ở URL gốc.
- MIME type như `text/css`, `text/html`, `image/svg+xml` thường được xác định theo loại tệp và cấu hình framework/container. Không nên hardcode một danh sách header phụ như `Content-Length` hoặc `Last-Modified` vì chúng có thể khác khi chạy.
- Trình duyệt có thể gửi các request CSS/JS/ảnh riêng sau khi tải HTML. Một trang HTML mở được nhưng CSS lỗi không có nghĩa “Spring đã phục vụ tất cả file thành công”.

### 4.1. Trang chào (welcome page)

Nếu tìm thấy `index.html` trong các vị trí static được cấu hình, Spring Boot có thể dùng nó làm **welcome page** tại `GET /`. Nếu không có `index.html` tĩnh, Boot có thể xét template `index` khi engine template phù hợp hiện diện. Welcome page là một cơ chế **fallback**, nên mapping rõ ràng cho `/` có thể được ưu tiên hơn.

Tệp `static/index.html` vẫn có URL `GET /index.html`. Cần phân biệt “file `index.html` được phục vụ” với “`/` trỏ đến welcome page”: khi thay đổi cấu hình pattern hoặc thêm controller, hãy kiểm tra cả hai đường dẫn.

Tương tự, `favicon.ico` ở một static location có thể được Spring Boot phát hiện để phục vụ favicon, nhưng trình duyệt và cache có thể khiến bạn thấy biểu tượng cũ sau khi thay file.

## 5. Ví dụ hoàn chỉnh chạy được với Spring Boot 3.3.x và Java 17

Ví dụ sau tạo **một ứng dụng độc lập** không cần database, frontend build tool hay controller tùy chỉnh. Mục tiêu là chứng minh từng thư mục phục vụ HTTP.

### 5.1. Cấu trúc dự án

~~~text
assets-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/assetsdemo/
    │   └── AssetsDemoApplication.java
    └── resources/
        ├── application.properties
        ├── static/
        │   ├── index.html
        │   └── css/site.css
        ├── public/
        │   └── about.html
        ├── resources/
        │   └── docs/guide.txt
        └── META-INF/
            └── resources/
                └── icons/logo.svg
~~~

Tạo chính xác các đường dẫn trong cây trên. Những ví dụ mã dưới đây tương ứng với **toàn bộ nội dung** từng tệp.

**`pom.xml`**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>assets-demo</artifactId>
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

`spring-boot-starter-web` đưa vào Spring MVC và embedded Tomcat theo mặc định; không cần cấu hình resource handler để thử bốn thư mục. Spring Boot parent quản lý phiên bản các dependency tương ứng.

**`src/main/java/com/example/assetsdemo/AssetsDemoApplication.java`**

~~~java
package com.example.assetsdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AssetsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AssetsDemoApplication.class, args);
    }
}
~~~

Chỉ một lớp `main` để chạy, không cần controller. Vị trí package nằm dưới `com.example.assetsdemo` đúng như cấu trúc cây.

**`src/main/resources/application.properties`**

~~~properties
server.port=8080
~~~

Không đặt `spring.web.resources.static-locations` hoặc `spring.mvc.static-path-pattern` trong bài lab ban đầu để sử dụng **mặc định**.

**`src/main/resources/static/index.html`**

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Spring Boot Static Resources</title>
  <link rel="stylesheet" href="/css/site.css">
</head>
<body>
  <h1>Trang index tĩnh</h1>
  <p>Trang này được đọc từ classpath:/static/index.html.</p>
  <img src="/icons/logo.svg" alt="Hình tròn minh họa" width="80" height="80">
  <p><a href="/about.html">Trang public</a></p>
  <p><a href="/docs/guide.txt">Tài liệu resources</a></p>
</body>
</html>
~~~

Đường dẫn `href="/css/site.css"`, `src="/icons/logo.svg"` là đường dẫn **tính từ root URL của ứng dụng** trong lab (context path mặc định là `/`). Nếu sau này đặt ứng dụng dưới context path khác, phải điều chỉnh cách dựng link để dùng đúng prefix, hoặc dùng công cụ sinh URL theo context.

**`src/main/resources/static/css/site.css`**

~~~css
body {
  font-family: system-ui, sans-serif;
  max-width: 720px;
  margin: 2rem auto;
  line-height: 1.6;
}
h1 {
  color: #14532d;
}
img {
  display: block;
  margin-top: 1rem;
}
~~~

CSS có URL `/css/site.css`, **không** phải `/static/css/site.css`.

**`src/main/resources/public/about.html`**

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>About</title>
</head>
<body>
  <h1>Trang public</h1>
  <p>Được phục vụ từ classpath:/public/about.html.</p>
</body>
</html>
~~~

File này được đọc trực tiếp từ `classpath:/public/about.html`, URL `/about.html`.

**`src/main/resources/resources/docs/guide.txt`**

~~~text
Tài liệu tĩnh trong classpath:/resources/docs/guide.txt.
Đường dẫn HTTP là /docs/guide.txt.
~~~

Phần `resources/resources` trên đường dẫn nguồn là **đúng**, không phải lỗi gõ.

**`src/main/resources/META-INF/resources/icons/logo.svg`**

~~~xml
<svg xmlns="http://www.w3.org/2000/svg"
     viewBox="0 0 80 80" width="80" height="80">
  <circle cx="40" cy="40" r="32" fill="#15803d"/>
  <circle cx="40" cy="40" r="12" fill="#ffffff"/>
</svg>
~~~

Tệp SVG nằm dưới `META-INF/resources` nhưng URL là `/icons/logo.svg`.

### 5.2. Chạy ứng dụng và kiểm tra URL

Trong thư mục `assets-demo`, cài Java 17+ và Maven 3.9+, chạy:

~~~bash
mvn spring-boot:run
~~~

Sau khi ứng dụng khởi động tại port 8080, mở các URL:

| URL | Nguồn trong dự án | Điều cần quan sát |
| --- | --- | --- |
| `http://localhost:8080/` | `static/index.html` | Trang chào có tiêu đề và các liên kết |
| `http://localhost:8080/index.html` | `static/index.html` | Cùng nội dung HTML từ file tĩnh |
| `http://localhost:8080/css/site.css` | `static/css/site.css` | Trả về văn bản CSS |
| `http://localhost:8080/about.html` | `public/about.html` | Trang HTML “Trang public” |
| `http://localhost:8080/docs/guide.txt` | `resources/docs/guide.txt` | Hai dòng văn bản hướng dẫn |
| `http://localhost:8080/icons/logo.svg` | `META-INF/resources/icons/logo.svg` | Nội dung SVG hoặc hình tròn minh họa |

Dùng `curl` để xem status và header:

~~~bash
curl -i http://localhost:8080/css/site.css
curl -i http://localhost:8080/about.html
curl -i http://localhost:8080/docs/guide.txt
curl -i http://localhost:8080/icons/logo.svg
~~~

Với file tồn tại, không có bảo mật chặn và chưa thay đổi cấu hình, kỳ vọng mỗi request trả **200 OK**. `Content-Type` thông thường sẽ phù hợp loại tệp (CSS, HTML, text, SVG). Các header khác có thể thay đổi theo container, framework, cách gọi và cache. Khi thử trên PowerShell cũ, gọi `curl.exe` để tránh xung đột alias `curl`.

Bạn cũng có thể thử một URL sai:

~~~bash
curl -i http://localhost:8080/static/css/site.css
~~~

Kỳ vọng **404 Not Found** vì trong cấu trúc ví dụ không có tệp tương đối `static/css/site.css` **bên trong** bất kỳ nguồn static nào. Tiền tố vật lý `static` không tự động là tiền tố URL.

### 5.3. Đóng gói executable JAR

Dừng lệnh `mvn spring-boot:run` rồi chạy:

~~~bash
mvn clean package
jar tf target/assets-demo-0.0.1-SNAPSHOT.jar
java -jar target/assets-demo-0.0.1-SNAPSHOT.jar
~~~

Khi xem danh sách bằng `jar tf`, tìm các entry tương ứng:

~~~text
BOOT-INF/classes/static/index.html
BOOT-INF/classes/static/css/site.css
BOOT-INF/classes/public/about.html
BOOT-INF/classes/resources/docs/guide.txt
BOOT-INF/classes/META-INF/resources/icons/logo.svg
~~~

`jar tf` liệt kê cả nhiều entry khác; năm dòng trên là các **đường dẫn cần tìm**, không phải toàn bộ stdout. Sau khi chạy JAR, gọi lại các URL ở mục 5.2; nếu file đã được đóng gói đúng, URL vẫn hoạt động với cơ chế classpath mặc định. Đây là bài kiểm chứng quan trọng: không được nhầm việc IDE nhìn thấy file với việc artifact phát hành thực sự có file đó.

## 6. Các cấu hình thay đổi URL và vị trí tìm tệp

Có hai loại cấu hình riêng; phải phân biệt khi xử lý 404.

### 6.1. Đổi **URL pattern**: spring.mvc.static-path-pattern

Giữ nguyên cấu trúc thư mục của ví dụ, nhưng thêm vào `application.properties`:

~~~properties
spring.mvc.static-path-pattern=/assets/**
~~~

Khi đó pattern tiếp nhận static asset đổi từ `/**` sang `/assets/**`. Một số URL ví dụ:

| Tệp nguồn | URL mới |
| --- | --- |
| `static/css/site.css` | `/assets/css/site.css` |
| `public/about.html` | `/assets/about.html` |
| `resources/docs/guide.txt` | `/assets/docs/guide.txt` |
| `META-INF/resources/icons/logo.svg` | `/assets/icons/logo.svg` |

**Không có chuyện các file chuyển thư mục trên đĩa**: chỉ đường dẫn HTTP đổi. Các liên kết gốc trong `index.html`, như `href="/css/site.css"`, lúc này phải được sửa theo pattern mới để trình duyệt tải được CSS. Hãy kiểm tra riêng xử lý welcome page ở `/` khi thay đổi pattern; đừng suy đoán rằng `/` có hành vi hoàn toàn giống đường dẫn tĩnh mặc định.

### 6.2. Đổi **thư mục nguồn**: spring.web.resources.static-locations

Giả sử bạn tự tạo:

~~~text
src/main/resources/my-assets/
  notice.txt
~~~

Có thể cấu hình:

~~~properties
spring.web.resources.static-locations=classpath:/my-assets/
~~~

Khi chạy với URL pattern mặc định `/**`, `GET /notice.txt` được tìm trong `classpath:/my-assets/`. **Cấu hình này thay thế danh sách static locations mặc định**, không tự động nối thêm `static`, `public`, `resources`, `META-INF/resources`. Ở Spring MVC/Servlet, root `ServletContext` còn có quy tắc bổ sung riêng, nhưng không nên dựa vào đó để giữ các vị trí classpath đã bị thay thế.

Nếu muốn giữ bốn nguồn mặc định và thêm một nguồn custom, hãy liệt kê rõ các nguồn classpath cần giữ cùng nguồn mới. Ví dụ:

~~~properties
spring.web.resources.static-locations=classpath:/static/,classpath:/public/,classpath:/resources/,classpath:/META-INF/resources/,classpath:/my-assets/
~~~

Thứ tự vị trí có thể ảnh hưởng lựa chọn khi trùng tên. Cách an toàn hơn là **không tạo trùng đường dẫn public** giữa các nguồn. Cấu hình này thay đổi **nơi tìm** chứ không tự tạo prefix `/my-assets/` trong URL.

### 6.3. Đổi cả hai

Hai thuộc tính là hai chiều độc lập:

~~~properties
spring.mvc.static-path-pattern=/assets/**
spring.web.resources.static-locations=classpath:/my-assets/
~~~

Với file `src/main/resources/my-assets/notice.txt`, URL sẽ là `GET /assets/notice.txt`. Nếu cố gọi `GET /notice.txt`, nó không còn khớp static handler theo pattern trên.

### 6.4. Tắt ánh xạ tài nguyên tĩnh tự động

~~~properties
spring.web.resources.add-mappings=false
~~~

Thiết lập này tắt các static resource mappings do Spring Boot cấu hình tự động. Khi dùng nó, việc chỉ đặt file ở `src/main/resources/static` **không đủ** để có URL phục vụ file nữa; bạn phải cung cấp cơ chế phục vụ tài nguyên thích hợp nếu ứng dụng vẫn cần asset.

### 6.5. Tùy biến qua WebMvcConfigurer

Nếu cần một URL riêng và một nguồn riêng, bạn có thể đăng ký thêm resource handler trong Spring MVC. Đoạn sau là một **cấu hình Java bổ sung cho dự án Boot**, không phải chương trình `main` độc lập:

~~~java
package com.example.assetsdemo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class ExtraResourceConfig implements WebMvcConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/manuals/**")
                .addResourceLocations("classpath:/manuals/");
    }
}
~~~

Nếu tạo `src/main/resources/manuals/install.txt`, handler này phục vụ `GET /manuals/install.txt`. Class file phải đặt tại `src/main/java/com/example/assetsdemo/ExtraResourceConfig.java` để package đúng với ví dụ. Đây là **handler bổ sung**; không phải yêu cầu để bật bốn static locations mặc định.

**Lưu ý về `@EnableWebMvc`:** việc thêm `@EnableWebMvc` khiến bạn tự chịu trách nhiệm phần lớn cấu hình MVC và có thể làm mất auto-configuration mà Spring Boot thiết lập. Với nhu cầu thêm một handler, triển khai `WebMvcConfigurer` như ví dụ mà không thêm `@EnableWebMvc` là cách đơn giản hơn.

## 7. Phân biệt các thư mục dễ nhầm

| Vị trí | Mục đích | Mặc định có được phục vụ trực tiếp qua URL như static không? |
| --- | --- | --- |
| `src/main/resources/static` | Asset cho frontend | Có, qua resource handler |
| `src/main/resources/public` | Asset cho frontend | Có |
| `src/main/resources/resources` | Asset cho frontend | Có |
| `src/main/resources/META-INF/resources` | Asset web hoặc asset trong dependency JAR | Có |
| `src/main/resources/templates` | Template server-side như Thymeleaf, FreeMarker | **Không** như file tĩnh; được view engine render khi được gọi đúng cách |
| `src/main/resources/application.properties` | Cấu hình ứng dụng | **Không**, không nằm trong nguồn static mặc định |
| `src/main/java` | Mã nguồn Java | Không phải thư mục asset tĩnh |
| `src/main/webapp` | Tài nguyên web truyền thống cho WAR | **Không nên dùng** để phục vụ tài nguyên khi đóng gói Spring Boot executable JAR |

Ví dụ, `templates/profile.html` có thể chứa cú pháp như `th:text` của Thymeleaf, nhưng nếu chuyển file này vào `static`, Spring phục vụ nội dung tệp như một asset tĩnh; **các biểu thức template không tự được render** theo dữ liệu controller. Ngược lại, `static/index.html` có thể hoạt động mà không cần template engine.

Một tệp cấu hình nội bộ như `application.yml` không được đặt vào `static` hoặc `public`, vì đó là những vùng có thể truy cập qua HTTP. Đặc biệt tránh cấu hình `spring.web.resources.static-locations=classpath:/`: mở rộng nguồn tĩnh ra toàn bộ gốc classpath có thể vô tình đưa file cấu hình và nội dung riêng tư vào phạm vi có thể phục vụ.

## 8. Bảo mật, cache, WebJars và xung đột routing

### 8.1. “Public” không tự bỏ qua Spring Security

Tên thư mục `public` không phải cấu hình authorization. Khi thêm **Spring Security** vào ứng dụng, filter chain có thể yêu cầu xác thực đối với cả `/css/site.css`, `/about.html` hoặc `/icons/logo.svg`, tùy chính sách bạn đặt.

Muốn asset thật sự công khai, cần cho phép các đường dẫn URL cần thiết theo cấu hình bảo mật, chẳng hạn các mẫu `/css/**`, `/icons/**` và `/about.html`. Kiểm tra bằng request chưa đăng nhập. Đừng suy ra từ việc file ở `public` mà endpoint sẽ tự bỏ qua security. Với file nhạy cảm/riêng cho từng người dùng, hãy xây dựng cơ chế kiểm soát truy cập thay vì nhét tệp vào một static location công khai.

### 8.2. Cache và cập nhật file

Browser/proxy có thể cache CSS, JS, hình ảnh. Nếu sau deploy trình duyệt vẫn thấy nội dung cũ, hãy xem Network tab, `Cache-Control`, `ETag`/`Last-Modified` nếu có, status `304 Not Modified` và tên file được request.

Spring MVC hỗ trợ xử lý cache, conditional request và chiến lược versioning cho static resources. Khi phục vụ asset lâu dài, có thể dùng tên URL chứa version/hash nội dung để tránh browser dùng mã cũ. Việc bật chiến lược version cần đi kèm cách sinh URL tham chiếu đúng; chỉ bật cấu hình mà giữ link cố định chưa chắc đạt kết quả mong muốn.

### 8.3. WebJars và META-INF/resources

WebJars đóng gói thư viện giao diện dưới dạng dependency JAR. Spring Boot hỗ trợ cơ chế `/webjars/**` cho những dependency tuân theo cấu trúc WebJar; dạng URL thực tế còn phụ thuộc tên thư viện và phiên bản. Đây là một ví dụ về lý do `META-INF/resources` tồn tại, nhưng **không phải** mọi dependency Java mang asset web đều tự có đường dẫn `/webjars/**`.

### 8.4. Xung đột với route động

Giả sử bạn có tệp `static/reports.html` và controller khai báo `@GetMapping("/reports.html")`. Hai cơ chế cùng nhắm đến URL đó. Mapping controller thông thường được ưu tiên hơn resource handler mặc định. Vì vậy khi thấy file tồn tại nhưng nội dung khác kỳ vọng, hãy kiểm tra **route được ứng dụng đăng ký** thay vì chỉ kiểm tra file.

Tương tự, static handler `/**` rộng có thể nhận đường dẫn còn lại khi không có controller khớp. Spring MVC phiên bản mới có thể báo `NoResourceFoundException` cho URL thiếu static resource, thay vì ngoại lệ “no handler” như bạn dự kiến. Mã HTTP cuối thường vẫn là 404; phân biệt loại exception hữu ích khi viết `@ControllerAdvice`.

## 9. Chẩn đoán lỗi tài nguyên tĩnh theo từng lớp

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách kiểm tra/xử lý |
| --- | --- | --- |
| `GET /static/css/site.css` trả 404 | Sai URL: thêm nhầm tên thư mục nguồn `static` | Dùng `/css/site.css` với cấu hình mặc định |
| `GET /docs/guide.txt` trả 404 | Đặt `guide.txt` ở gốc `src/main/resources/docs`, chưa vào static location | Di chuyển đến `src/main/resources/resources/docs/guide.txt` hoặc nguồn phù hợp |
| Chạy IDE thấy file, chạy JAR thì 404 | File không được đóng gói hoặc build sử dụng artifact cũ | `mvn clean package`, dùng `jar tf ...` xác minh entry trong `BOOT-INF/classes` |
| Từ lúc đổi `static-locations`, CSS cũ bị 404 | Property **thay** bốn thư mục mặc định | Liệt kê lại các nguồn cần giữ hoặc chuyển file sang nguồn mới |
| Từ lúc đổi `static-path-pattern`, trang mất CSS | URL trong HTML còn là `/css/...` nhưng pattern mới là `/assets/**` | Đồng bộ link với pattern mới |
| Bị redirect đến login, 401 hoặc 403 | Spring Security chặn URL asset | Kiểm tra SecurityFilterChain và requestMatchers cho URL cần public |
| Trang HTML tải được nhưng logo/CSS không xuất hiện | Asset URL sai, lỗi chữ hoa/thường, bị cache hoặc bị chặn | Xem Network tab, request/status từng asset |
| Local chạy, Linux/container 404 | Chữ hoa/thường tên file khác nhau; file chưa copy vào image | Kiểm tra chính xác tên và nội dung image/JAR |
| Thay file nhưng trình duyệt vẫn thấy bản cũ | Browser/proxy cache hoặc deploy chưa cập nhật artifact | Kiểm tra response headers, URL version và file thực tế trong JAR |
| `GET /` không hiện `index.html` | Có route `/` khác, welcome page bị thay đổi hoặc static location khác | Kiểm tra route, `static-locations`, welcome page và pattern |
| Không thể truy cập file trong `templates` bằng URL trực tiếp | Đó là nguồn template, không phải static root | Render qua view engine hoặc đặt đúng file tĩnh trong static location |

Quy trình tìm nguyên nhân nhanh, theo đúng thứ tự:

1. **Xác nhận URL** đang được trình duyệt request, bao gồm context path và prefix nếu có. Trong ví dụ mặc định, `/css/site.css` đúng còn `/static/css/site.css` sai.
2. **Xác nhận file trên classpath** bằng cây dự án và artifact đã build, không chỉ bằng IDE. Trong executable JAR, tìm `BOOT-INF/classes/static/css/site.css`.
3. **Xem cấu hình** `spring.web.resources.static-locations`, `spring.mvc.static-path-pattern`, `spring.web.resources.add-mappings` và các `WebMvcConfigurer`.
4. **Phân biệt status**: 404 thường là route/file không tìm được; 401/403 thường là authorization; 304 và nội dung cũ gợi ý cache; 500 cần xem exception phía server.
5. **Kiểm tra va chạm** giữa tài nguyên trùng URL, mapping controller và ứng dụng đóng gói khác nhau giữa local/production.

**Không dùng đường dẫn tuyệt đối trên filesystem làm bằng chứng rằng classpath có file.** Một thư mục có sẵn trên máy developer có thể vắng trong Docker image; packaging mới là điểm quyết định khi chạy ứng dụng đã phân phối.

## 10. Spring WebFlux và WAR: phần nào giống, phần nào khác?

Với Spring Boot **WebFlux**, các nguồn classpath mặc định `/static`, `/public`, `/resources`, `/META-INF/resources` vẫn áp dụng, nhưng resource handler là `ResourceWebHandler` thay vì `ResourceHttpRequestHandler` của MVC. Khi muốn đổi static URL pattern trong WebFlux, dùng:

~~~properties
spring.webflux.static-path-pattern=/assets/**
~~~

Đừng dùng `spring.mvc.static-path-pattern` để mong đổi route của ứng dụng WebFlux thuần. Thuộc tính `spring.web.resources.static-locations` được sử dụng để đổi nguồn tìm tài nguyên trong các trường hợp phù hợp. WebFlux không dựa trên cấu trúc `src/main/webapp` của Servlet WAR như một nguồn classpath mặc định.

Với **Servlet WAR** triển khai vào một container có `ServletContext`, root của ServletContext là một nguồn tài nguyên web có liên quan. Điều này khác với bài lab **executable JAR**, nơi nên dùng các thư mục classpath đã mô tả. Đừng chuyển các tài nguyên sang `src/main/webapp` chỉ vì từng thấy cấu trúc này ở dự án JSP/WAR truyền thống: Spring Boot cảnh báo thư mục đó không phù hợp khi đóng gói JAR.

## 11. Tự kiểm tra kiến thức

**Câu 1.** Tệp `src/main/resources/static/images/photo.png`, giữ cấu hình MVC mặc định. URL nào đúng: `/static/images/photo.png` hay `/images/photo.png`? Vì sao?

**Câu 2.** Giải thích tại sao `src/main/resources/docs/manual.txt` khác `src/main/resources/resources/docs/manual.txt` ở góc nhìn HTTP public.

**Câu 3.** Bạn đặt `src/main/resources/META-INF/resources/icons/app.svg`. Người dùng phải gọi URL nào? Nếu đưa tệp đó vào dependency JAR theo cùng cấu trúc, Spring Boot được thiết kế để xử lý kiểu tài nguyên đó như thế nào?

**Câu 4.** Sau khi đặt `spring.mvc.static-path-pattern=/assets/**`, vì sao `<link href="/css/site.css">` không tải được stylesheet như trước?

**Câu 5.** Sau khi đặt `spring.web.resources.static-locations=classpath:/custom/`, bốn nguồn classpath mặc định có còn được liệt kê tự động không?

**Câu 6.** Vì sao đặt `private-token.txt` trong `public` là một thiết kế không an toàn nếu nội dung không được phép công khai?

**Câu 7.** Nếu file tồn tại trong source nhưng chạy JAR báo 404, ba việc cần kiểm tra ngay là gì?

**Đáp án và giải thích:**

1. `/images/photo.png`. Thư mục `static` là nguồn tìm kiếm, không phải segment URL mặc định.
2. Chỉ đường dẫn thứ hai nằm trong `classpath:/resources/` mặc định; đường dẫn thứ nhất ở classpath root nhưng không tự là static location.
3. `/icons/app.svg`. Spring có thể phục vụ asset từ các nguồn classpath thích hợp, gồm nội dung đóng gói trong dependency JAR, nếu không bị cấu hình/security chặn hoặc va chạm.
4. URL pattern đã đổi sang `/assets/**`, nên link mới phải dùng `/assets/css/site.css` trong cấu hình ví dụ.
5. Không. Cấu hình `static-locations` thay danh sách mặc định; nếu muốn giữ, phải liệt kê các nguồn cần giữ.
6. Static resource có thể truy cập qua URL nếu không có lớp bảo mật chặn; file nhạy cảm không nên nằm trong vùng phục vụ công khai.
7. Kiểm tra URL/pattern, entry thật trong executable JAR (`jar tf`), và `static-locations` cùng các thay đổi security/handler.

## 12. Ghi nhớ khi thiết kế ứng dụng

- Hãy chọn **một cách sắp xếp nhất quán**, chẳng hạn đặt asset ứng dụng vào `static/` và giữ `META-INF/resources/` cho trường hợp thực sự cần tuân theo quy ước đóng gói JAR/Servlet.
- Hiểu chính xác đường dẫn hai cấp: `src/main/resources` là **gốc nguồn**, còn `static`, `public`, `resources` và `META-INF/resources` là **các thư mục con trên classpath** được Spring Boot chọn làm static roots.
- Đừng thêm tên static root vào URL trừ khi chính bạn đã tạo ra đường dẫn đó ở bên trong nội dung asset hoặc thay đổi URL mapping.
- Khi định cấu hình `static-locations`, nhớ rằng nó **thay** danh sách nguồn mặc định. Khi định cấu hình `static-path-pattern`, nhớ cập nhật đường dẫn URL tham chiếu trong trang.
- Xác minh cả **HTTP response lẫn nội dung executable JAR** trước khi kết luận static resources hoạt động ổn định.
- Xem security, cache và context path là một phần của đường đi request thực tế; “file nằm đúng thư mục” chỉ là một điều kiện.

## 13. Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Servlet Web Applications, mục Static Content và Welcome Page: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Framework — Static Resources trong Spring MVC: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html
- Spring Boot 3.3 — Reactive Web Applications (khi dùng WebFlux): https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Boot — Maven Plugin và executable archive: https://docs.spring.io/spring-boot/3.3/maven-plugin/reference/htmlsingle/
