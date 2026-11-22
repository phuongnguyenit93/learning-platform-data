# Phòng tránh path traversal và chỉ công bố thư mục được cho phép trong Spring Boot

## 1. Mục tiêu và mô hình an toàn

Một ứng dụng Spring Boot có thể phục vụ CSS, JavaScript, ảnh, font, tài liệu công khai và nhiều tài nguyên tĩnh khác. Vấn đề bảo mật xuất hiện khi ứng dụng để URL hoặc dữ liệu người dùng quyết định đường dẫn đọc file mà không giới hạn chặt chẽ phạm vi được phép. Kẻ tấn công có thể thử **path traversal (directory traversal)** để yêu cầu file nằm ngoài thư mục công khai, ví dụ file cấu hình, khóa bí mật hoặc dữ liệu nội bộ.

Sau bài này, bạn có thể:

1. Phân biệt **URL công khai** với **đường dẫn file thực** và hiểu cách traversal đi qua các lớp URL decoding, path normalization, resource resolution.
2. Sử dụng cấu hình Spring MVC chuẩn để chỉ công bố các resource trong **một thư mục được cho phép**, thay vì tự nối đường dẫn từ tham số HTTP.
3. Nhận diện các bề mặt rủi ro: thư mục classpath mặc định, mapping quá rộng, file-system resource, symbolic link, reverse proxy, controller đọc file thủ công và cấu hình phiên bản Spring Framework chưa được vá.
4. Viết ứng dụng Spring Boot Java 17+ và kiểm thử **file được phép thì đọc được, file ngoài thư mục cho phép phải bị từ chối**.
5. Phân biệt giới hạn đường dẫn với **xác thực, phân quyền và quyền đọc file của hệ điều hành**.

**Nguyên tắc:** xác định tập tài nguyên công khai từ phía server; ánh xạ một URL prefix cụ thể đến thư mục công khai cụ thể; không nhận đường dẫn tuyệt đối/tương đối tùy ý từ client để tạo tài nguyên trả về.

## 2. Path traversal là gì?

Giả sử ứng dụng chỉ nên phục vụ file trong thư mục:

```text
application
├─ public-assets/
│  ├─ logo.svg
│  └─ css/site.css
└─ internal/
   ├─ config-private.txt
   └─ customer-data.csv
```

Yêu cầu hợp lệ: `GET /assets/logo.svg` → resource `public-assets/logo.svg`.

Yêu cầu nguy hiểm, nếu endpoint tự ghép chuỗi không kiểm soát: `GET /assets/../internal/config-private.txt`. Thành phần `..` biểu thị **thư mục cha** khi đường dẫn được diễn giải trong hệ thống file. Nếu ứng dụng nối string URL vào filesystem path và không kiểm soát, việc chuẩn hóa có thể làm đường dẫn trỏ sang `internal/config-private.txt`.

Đây là ví dụ về một lỗi có thể xảy ra trong controller tự viết:

```java
// VÍ DỤ KHÔNG AN TOÀN: không sử dụng để phục vụ file.
Path file = Path.of("/srv/app/public-assets")
    .resolve(userSuppliedPath);
return Files.readAllBytes(file);
```

Đoạn này chỉ minh họa nguyên nhân, không phải chương trình độc lập. `userSuppliedPath` do request quyết định; phép `resolve` **không mặc nhiên bảo đảm** file nằm trong root. Tương tự, một chuỗi tuyệt đối có thể làm `resolve` bỏ qua phần root tùy hệ điều hành và định dạng path.

Các biến thể cần có trong threat model:

- Đường dẫn cha: `../`, `../../`; trên Windows còn phải xem xét dấu gạch ngược `\`.
- URL encoding của dấu chấm hoặc dấu phân tách, ví dụ `%2e%2e%2f`; có thể bị xử lý khác nhau ở proxy, servlet container và ứng dụng.
- **Nhiều tầng decode**: dữ liệu được decode một lần ở proxy, thêm lần nữa trong code riêng sẽ có cách hiểu khác.
- Dạng tuyệt đối, ổ đĩa Windows, UNC path hoặc đường dẫn có ký tự phân tách thay thế.
- **Symbolic link** trong thư mục công khai trỏ đến file nằm ngoài thư mục.
- Cấu hình handler/resource resolver sai, hoặc dependency framework còn lỗ hổng đã công bố.

Không có một phép `replace("../", "")`, regex đơn giản hay việc kiểm tra đường dẫn “có bắt đầu bằng chuỗi root” là biện pháp phòng thủ đầy đủ.

## 3. Hiểu cơ chế tài nguyên tĩnh mặc định của Spring Boot

Với **Spring Boot MVC** dùng `spring-boot-starter-web`, Boot thường phục vụ static assets từ các thư mục classpath sau:

- `classpath:/static/`
- `classpath:/public/`
- `classpath:/resources/`
- `classpath:/META-INF/resources/`

Trong ứng dụng Servlet, còn có nguồn resource theo **root của `ServletContext`**. Mapping tài nguyên tĩnh mặc định thường ở `/**`. Spring MVC dùng `ResourceHttpRequestHandler`; Spring WebFlux dùng `ResourceWebHandler`. Các handler sử dụng cơ chế resource resolver của framework, có kiểm tra resource nằm dưới location đã cấu hình.

Ví dụ file `src/main/resources/static/css/app.css` thường có URL `/css/app.css`. Không cần viết controller như `@GetMapping("/{path}")` để đọc file theo tên request.

Tuy nhiên, **“Spring Boot phục vụ sẵn” không có nghĩa mọi file đặt trong dự án đều là public**; chỉ các tài nguyên nằm ở nguồn được cấu hình cho static handler mới nên được xem là public. Ngược lại, bất kỳ file nhạy cảm nào bị vô tình đặt trong `static/`, `public/` hoặc thư mục được mapping công khai có thể truy cập mà không cần traversal.

Hai property hữu ích trong Spring MVC:

```properties
# Thay URL pattern của cấu hình static resource mặc định:
spring.mvc.static-path-pattern=/assets/**

# Thay các location mặc định bằng location được chọn:
spring.web.resources.static-locations=classpath:/public-assets/
```

Đây là cách cấu hình đơn giản khi muốn đổi URL prefix và nguồn asset. Tuy vậy, với Servlet, Spring Boot có quy tắc về resource từ **ServletContext root** được thêm vào; vì mục tiêu của bài là một vùng công khai có kiểm soát **chặt chẽ**, ví dụ chính phía dưới sẽ tắt auto static mappings và khai báo rõ resource handler duy nhất.

**Đừng nhầm:**

- `spring.mvc.static-path-pattern` thay URL được map, **không phải** bảo vệ file trên đĩa.
- `spring.web.resources.static-locations` chọn các nguồn file/classpath; không nên trỏ vào thư mục dự án gốc, home directory, đường dẫn chứa cấu hình hoặc thư mục upload có nội dung không được duyệt.
- `spring.web.resources.add-mappings=false` tắt các static resource mappings do Spring Boot tự thêm; nó không tự biến mọi handler tùy chỉnh thành an toàn.

## 4. Phương án khuyến nghị: chỉ có một URL prefix cho thư mục classpath công khai

Với asset đi kèm bản phát hành, lựa chọn dễ kiểm soát là đặt chúng trong một thư mục **riêng, chỉ chứa nội dung public**, ví dụ `src/main/resources/public-assets/`, rồi đăng ký **một** mapping rõ ràng `/assets/**` đến `classpath:/public-assets/`.

Sơ đồ:

```text
HTTP GET /assets/logo.svg
             |
             v
Spring MVC ResourceHttpRequestHandler
             |
             v
classpath:/public-assets/logo.svg  ---> 200 (nếu file có thật)

HTTP GET /assets/../internal/example.txt
             |
             v
URL normalization / security checks / ResourceHandler
             |
             v
Không được trả nội dung ngoài vùng public ---> 4xx
```

Tài nguyên nội bộ phải nằm **ngoài** location mà handler được phép phục vụ; thư mục public không chứa dữ liệu nhạy cảm.

### 4.1. Cấu trúc dự án mẫu

Tạo dự án Spring Boot tương thích Java **17+**, với dependency **Spring Web** (`spring-boot-starter-web`). Sử dụng một phiên bản Spring Boot được hỗ trợ và có các bản vá bảo mật mới của Spring Framework.

```text
src/
├─ main/
│  ├─ java/com/example/demo/
│  │  ├─ StaticAssetsApplication.java
│  │  └─ StaticAssetsConfiguration.java
│  └─ resources/
│     ├─ application.properties
│     ├─ public-assets/
│     │  └─ hello.txt
│     └─ internal-demo/
│        └─ marker.txt
└─ test/
   └─ java/com/example/demo/
      └─ StaticAssetsApplicationTest.java
```

**`internal-demo/marker.txt` chỉ là fixture giả lập** để minh họa file nằm ngoài vùng public, không chứa bí mật thật. Trong ứng dụng thực tế, không đóng gói secret hay dữ liệu nhạy cảm trong classpath và repository chỉ để “trông như private”.

### 4.2. File cấu hình

**`src/main/resources/application.properties`**

```properties
server.port=8080

# Tắt các static resource handlers mà Boot tự thêm.
spring.web.resources.add-mappings=false
```

**`src/main/java/com/example/demo/StaticAssetsApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StaticAssetsApplication {
    public static void main(String[] args) {
        SpringApplication.run(StaticAssetsApplication.class, args);
    }
}
```

**`src/main/java/com/example/demo/StaticAssetsConfiguration.java`**

```java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class StaticAssetsConfiguration implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/public-assets/");
    }
}
```

**`src/main/resources/public-assets/hello.txt`**

```text
PUBLIC_ASSET
```

**`src/main/resources/internal-demo/marker.txt`**

```text
NOT_FOR_HTTP
```

Các điểm cần hiểu:

1. `spring.web.resources.add-mappings=false` ngăn Boot tự thêm mapping static mặc định quá rộng; handler do `WebMvcConfigurer` định nghĩa vẫn hoạt động trong Spring MVC.
2. `addResourceHandler("/assets/**")` chỉ áp dụng cho URL bắt đầu bằng `/assets/` theo cơ chế path matching của Spring MVC.
3. `addResourceLocations("classpath:/public-assets/")` giới hạn nguồn asset ở thư mục riêng trên classpath; **dấu `/` cuối location** làm rõ đây là một thư mục.
4. `ResourceHttpRequestHandler` dùng resource resolution chuẩn của Spring; mặc định `PathResourceResolver` kiểm tra tài nguyên được tìm thấy nằm dưới các location hợp lệ. Không cần thay bằng resolver tự viết để “tối ưu” trước khi hiểu đầy đủ kiểm tra bảo mật.
5. Không có mapping cho `/internal-demo/marker.txt` hoặc tài nguyên `internal-demo/`. File ở classpath **không tự trở thành public chỉ vì nằm cạnh resource khác**.
6. Không khai báo thêm mapping `/**`, `classpath:/`, `file:/`, servlet default-handler tùy biến hoặc endpoint đọc file thủ công nếu mục tiêu là chỉ công bố `public-assets/`.

Đây là cấu hình Spring MVC đầy đủ cho tình huống mẫu. Một hệ thống lớn có thể có thêm controller và handler khác; khi đó cần kiểm tra **tổng thể các route** có thể trả về resource, bao gồm gateway/CDN/proxy phía trước.

### 4.3. Chạy và kiểm tra qua HTTP

Trong thư mục dự án có Maven Wrapper:

```bash
./mvnw spring-boot:run
```

Trên Windows, chạy `mvnw.cmd spring-boot:run`. Dùng `curl.exe` nếu PowerShell đang ánh xạ `curl` thành cmdlet khác.

**Tài nguyên được phép:**

```bash
curl -i http://localhost:8080/assets/hello.txt
```

Kết quả mong đợi: HTTP **200**, response body là `PUBLIC_ASSET` (kèm newline cuối file); header cụ thể như `Content-Type` có thể phụ thuộc server và cấu hình.

**Không công bố thư mục khác:**

```bash
curl -i http://localhost:8080/internal-demo/marker.txt
curl -i http://localhost:8080/assets/internal-demo/marker.txt
curl -i http://localhost:8080/hello.txt
```

Trong ứng dụng mẫu, các URL này phải **không trả nội dung của file**, thường là HTTP **404**. URL cuối cũng cho thấy tài nguyên public chỉ có đường dẫn `/assets/hello.txt`, không tự được phục vụ ở `/hello.txt`.

**Thử traversal và encoded traversal:** sử dụng `--path-as-is` để curl không tự chuẩn hóa thành phần `..` trước khi gửi HTTP request.

```bash
curl --path-as-is -i "http://localhost:8080/assets/../internal-demo/marker.txt"
curl --path-as-is -i "http://localhost:8080/assets/%2e%2e/internal-demo/marker.txt"
curl --path-as-is -i "http://localhost:8080/assets/%252e%252e%252finternal-demo%252fmarker.txt"
```

Kỳ vọng an toàn: **không có request nào trả `NOT_FOR_HTTP`**. Tùy servlet container, reverse proxy, luật firewall và cách decode, status có thể là **400**, **404** hoặc một phản hồi từ chối khác. Không ép một HTTP status chính xác cho mọi kiểu URL bất thường khi chưa xác định chính xác tầng xử lý.

**Lưu ý:** chính việc endpoint trả 404 với tên file không tồn tại là một test yếu. Ví dụ này tạo một file marker **có thật** nhưng nằm ngoài thư mục public, rồi kiểm tra cả URL trực tiếp lẫn traversal. Khi làm kiểm thử bảo mật ngoài thực tế, dùng canary/fixture vô hại, không đặt hay yêu cầu đọc secret thật.

## 5. Kiểm thử tự động: contract “chỉ public-assets được phục vụ”

Dùng `spring-boot-starter-test` với dự án Spring Boot và test Spring MVC qua `MockMvc`. Nếu tạo dự án Spring Initializr, thêm dependency **Spring Boot Starter Test**.

Tạo **`src/test/java/com/example/demo/StaticAssetsApplicationTest.java`**:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class StaticAssetsApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void servesOnlyThePublishedAsset() throws Exception {
        mvc.perform(get("/assets/hello.txt"))
                .andExpect(status().isOk())
                .andExpect(content().string("PUBLIC_ASSET\n"));
    }

    @Test
    void doesNotServePrivateClasspathFolder() throws Exception {
        mvc.perform(get("/internal-demo/marker.txt"))
                .andExpect(status().isNotFound());

        mvc.perform(get("/assets/internal-demo/marker.txt"))
                .andExpect(status().isNotFound());
    }

    @Test
    void doesNotServeAssetAtUnapprovedUrl() throws Exception {
        mvc.perform(get("/hello.txt"))
                .andExpect(status().isNotFound());
    }
}
```

Chạy:

```bash
./mvnw test
```

Kết quả mong đợi: ba test pass trong dự án Spring Boot MVC mẫu. Đây là **kết quả dự kiến để bạn chạy kiểm chứng**, không phải báo cáo đã thực thi trên một repository cụ thể.

`MockMvc` phù hợp kiểm tra mapping của Spring MVC nhưng **không mô phỏng đầy đủ việc decode/normalize URL tại web server và reverse proxy thật**. Vì thế, trong CI hoặc môi trường staging còn cần các HTTP integration/security tests chạy trên đúng Tomcat/Jetty, gateway và HTTP client sẽ dùng khi triển khai. Test các biến thể raw, percent-encoded, double-encoded, slash/backslash và symlink trên hệ điều hành đích. Điều kiện kiểm thử là **không rò rỉ nội dung nằm ngoài vùng được phép**; 4xx nào cụ thể có thể do tầng mạng quyết định.

## 6. Đọc file theo yêu cầu trong controller: giải pháp khác static resource handler

Khi người dùng được tải file theo mã tài liệu, **đừng sử dụng đường dẫn file từ URL làm input truy cập filesystem trực tiếp**, ví dụ:

```java
// KHÔNG AN TOÀN: path lấy trực tiếp từ client.
@GetMapping("/download")
public byte[] download(@RequestParam String path) throws IOException {
    return Files.readAllBytes(
        Path.of("/srv/app/public-assets").resolve(path)
    );
}
```

Đây là đoạn minh họa rủi ro, cần import annotation và API tương ứng, **không phải code hoàn chỉnh để sử dụng**. Kể cả việc lọc chuỗi `"../"` hay chỉ kiểm tra `path.startsWith("/srv/app/public-assets")` cũng không đủ vì đường dẫn có thể encode khác, chứa `..`, dấu phân tách khác hoặc symlink.

Nếu thật sự cần API trả tài liệu riêng, thiết kế an toàn hơn là:

1. Client gửi **ID logic** của tài liệu, không phải filesystem path: `GET /documents/12345`.
2. Server kiểm tra **authentication + authorization theo tài liệu và tenant**.
3. Server tra ID trong database/map nội bộ để lấy đường dẫn do server lưu, không cho client thay thế tùy ý.
4. Root lưu trữ được định nghĩa từ cấu hình tin cậy và **quyền OS chỉ cho phép tiến trình đọc đúng file cần đọc**.
5. Resolve và canonicalize đường dẫn; kiểm tra target nằm trong root bằng `Path.startsWith(Path)` trên các `Path` đã chuẩn hóa/`toRealPath()`, **không dùng String.startsWith**. Kiểm tra file hiện hữu, regular file và không chứa symlink thoát root.
6. Xem xét **TOCTOU/symlink race**: nếu người dùng khác có thể thay file/link giữa bước kiểm tra và mở file, kiểm tra `toRealPath` chưa đủ chống race. Chọn vùng storage không cho tác nhân không tin cậy sửa cấu trúc, dùng API mở file an toàn theo platform khi cần.

Đoạn minh họa dưới đây cho thấy bước kiểm tra containment **sau khi file đã tồn tại**:

```java
// Minh họa nằm bên trong service; KHÔNG phải một HTTP endpoint hoàn chỉnh.
Path publicRoot = Path.of("/srv/app/published").toRealPath();
Path candidate = publicRoot.resolve(serverControlledRelativeName)
        .toRealPath();

if (!candidate.startsWith(publicRoot)
        || !Files.isRegularFile(candidate)) {
    throw new SecurityException("Requested file is not allowed");
}
```

`serverControlledRelativeName` phải do **server xác định từ ID đã được cấp quyền**, không phải chuỗi đường dẫn lấy nguyên từ request. `toRealPath()` yêu cầu path tồn tại, theo symlink và trả canonical real path. `startsWith(Path)` kiểm tra theo **thành phần đường dẫn**, giúp phân biệt `/srv/app/published` và `/srv/app/published-backup`. Cần bổ sung xử lý lỗi file không tồn tại, mở stream, response HTTP, authorization và vòng đời tài nguyên vào ứng dụng thật.

**Đừng cố tự xây dựng một static file server phức tạp** nếu `ResourceHttpRequestHandler` / `ResourceWebHandler` đã đáp ứng yêu cầu. Mỗi lớp decode, cache, normalize hay symbolic link tự thêm là một điểm có thể tạo lỗi mới.

## 7. Những rủi ro vẫn tồn tại dù dùng resource handler chuẩn

### 7.1. Công bố nhầm file bên trong vùng public

Handler có thể từ chối đọc **ngoài** root nhưng vẫn phục vụ **mọi file trong root**. Nếu ai đó copy `application-prod.yml`, bản backup, file `.env`, file chứa khóa, log, tài liệu riêng hoặc source map chứa dữ liệu nhạy cảm vào `public-assets/`, request hợp lệ có thể tải xuống.

Cách phòng tránh:

- Quy ước `public-assets/` chỉ chứa asset đã phê duyệt để công bố.
- Review thay đổi thư mục public; dùng script/CI kiểm kê artifact được đóng gói và chặn extension/tên file không được phép.
- Không copy toàn bộ repo, thư mục cấu hình hay mount secret vào document root.
- Không bật directory listing ở static web server/proxy; khi có file index tự động, kiểm tra rõ hành vi expose.
- Quy định MIME type, bảo vệ nội dung HTML/SVG/JS do người dùng upload; file upload không được tự chuyển thành executable active content trên cùng origin tin cậy.

### 7.2. Thêm vị trí tài nguyên quá rộng

Ví dụ những cấu hình cần **xem lại cẩn thận**:

```java
// Các ví dụ nguy hiểm nếu đây là root chứa dữ liệu không công khai.
registry.addResourceHandler("/**")
        .addResourceLocations("file:/srv/app/");

registry.addResourceHandler("/assets/**")
        .addResourceLocations("classpath:/");
```

Đây là snippet minh họa anti-pattern, không nên sao chép vào app. Mapping hoặc location quá rộng làm tăng tập file có thể được phục vụ. Dù framework kiểm tra path containment theo root, một root quá rộng vẫn cho phép truy cập rất nhiều file trong root đó.

Không thêm location như `file:/`, thư mục home, thư mục chứa file cấu hình, upload chưa kiểm duyệt hay ổ đĩa gốc. Cẩn thận với danh sách location nhiều phần tử vì **tập file public là hợp của các nguồn**.

### 7.3. Symbolic link và quyền hệ điều hành

Trên file system, một symlink nằm **bên trong** thư mục public có thể trỏ ra ngoài. Kiểm tra xử lý của framework theo phiên bản, bảo đảm không có symlink không tin cậy trong public tree; khi cần phục vụ file động, dùng canonical containment và thiết kế chống race như phần 6.

Dù có mapping đúng, hệ điều hành vẫn phải áp dụng **least privilege**: user chạy ứng dụng chỉ đọc tài nguyên phải được phục vụ, không được đọc secret hoặc thư mục của dịch vụ khác. Container mount và volume cũng cần giới hạn tương tự.

### 7.4. URL decoding và sự khác biệt giữa proxy, container, framework

Một request có thể đi qua:

```text
Client
  -> CDN / WAF
  -> reverse proxy / API gateway
  -> Tomcat/Jetty/Netty
  -> Spring MVC/WebFlux resource handler
  -> Resource/Filesystem
```

Mỗi tầng có thể xử lý dấu phân tách, URL encoding, encoded slash, backslash và dot segment khác nhau. Nếu một tầng kiểm soát đường dẫn trước khi decode nhưng tầng khác decode thêm lần nữa, policy có thể bị vượt qua.

Vì vậy:

- Duy trì phiên bản framework, servlet container và proxy được vá.
- Không gọi `URLDecoder.decode(...)` thêm tùy tiện trên file path đã được framework phân tích.
- Không xem rule ở proxy/WAF là thay thế cho việc giới hạn nguồn resource trong app.
- Chạy kiểm thử qua **đúng đường đi production**; thử payload chỉ với môi trường được phép.
- Kiểm tra file/route có thể truy cập qua cả HTTP 80 và HTTPS 443, qua host/path prefix khác hoặc từ CDN; chính sách phải nhất quán.

### 7.5. Authentication/authorization khác giới hạn directory

`permitAll("/assets/**")` (nếu ứng dụng dùng Spring Security) chỉ quyết định **ai được vào URL**, không đảm bảo handler chỉ mở file trong thư mục đúng. Ngược lại, map đúng directory không tự quyết định được file nào có tính riêng tư theo user.

**Tài nguyên tĩnh công khai** nên được đưa vào thư mục công khai không chứa dữ liệu riêng. **Tài liệu có phân quyền theo tài khoản/tenant** cần endpoint tải tài liệu kiểm tra quyền trước khi đọc, không nằm trong static directory được `permitAll`.

Nếu dùng Spring Security, ưu tiên cho request đến `/assets/**` đi qua security filter chain với quyền `permitAll` khi phù hợp. Đừng vô hiệu hóa các security filter bằng cách ignore toàn bộ request chỉ vì đó là static asset; các security headers và kiểm soát khác có thể hữu ích. Tên matcher phải khớp chính xác URL public mà bạn đã khai báo.

## 8. Bản vá Spring Framework quan trọng đối với path traversal

Không nên giả định “dùng resource handler chuẩn thì chắc chắn an toàn với mọi phiên bản”. Có các advisory thực tế:

**CVE-2024-38816** (công bố 12/09/2024): một số ứng dụng Spring MVC.fn/WebFlux.fn cấu hình `RouterFunctions` để phục vụ resource từ `FileSystemResource` bị path traversal; phiên bản Spring Framework 6.1.13 đã sửa nhánh 6.1. Thông tin chính thức: https://spring.io/security/cve-2024-38816/

**CVE-2026-41843** (công bố 08/06/2026): path traversal khi giải quyết **versioned static resources** trong Spring MVC/WebFlux với các điều kiện kết hợp, đặc biệt file-system resources và versioning support. Các bản vá công khai gồm Spring Framework **6.2.19** và **7.0.8**; các nhánh enterprise có bản vá riêng theo advisory. Thông tin chính thức: https://spring.io/security/cve-2026-41843/

Điểm rút ra:

1. **Nâng cấp Spring Boot/Spring Framework theo security advisory** và dùng bộ dependency được quản lý tương thích; không tự chỉ thay một Spring Framework jar rồi bỏ qua compatibility. Kiểm tra dependency tree và bản framework **đang được đóng gói/chạy**.
2. Nếu dùng resource versioning, file-system resource hoặc functional resource routes, xác định mình có nằm trong điều kiện ảnh hưởng của advisory hay không và nâng cấp lên bản được vá theo nhánh.
3. Ví dụ trong bài tránh file-system static root và không bật resource versioning; điều đó **giảm bề mặt rủi ro**, không thay thế nghĩa vụ cập nhật bản vá.
4. Vì lỗ hổng có thể xuất hiện trong framework, **không viết test rồi xem test pass là bằng chứng tuyệt đối**; tiếp tục theo dõi advisory, kiểm thử cả thư viện và container/proxy trong deployment.

## 9. Ghi chú cho Spring WebFlux và các loại web runtime khác

Ví dụ chính dùng **Spring MVC/Servlet**. Nếu dự án chạy **Spring WebFlux**, static handler tương ứng là `ResourceWebHandler`; cấu hình tùy chỉnh thông qua `WebFluxConfigurer`, không phải `WebMvcConfigurer`:

```java
// Ví dụ riêng cho ứng dụng Spring WebFlux.
@Configuration
public class ReactiveStaticConfig implements WebFluxConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/public-assets/");
    }
}
```

Đây là **snippet**, cần các import từ `org.springframework.context.annotation.Configuration` và `org.springframework.web.reactive.config`. Không đặt đồng thời lớp `WebMvcConfigurer` và `WebFluxConfigurer` trong dự án mẫu MVC; chọn cấu hình tương ứng với web stack thực tế.

Spring Boot WebFlux có property `spring.webflux.static-path-pattern`; property này **khác** `spring.mvc.static-path-pattern`. `spring.web.resources.static-locations` cũng có thể được dùng trong cấu hình static resources của Boot. Dù là MVC hay WebFlux, chính sách vẫn giống nhau: chỉ map location public cần thiết, cập nhật framework, kiểm tra URL decoding và kiểm thử file ngoài root không bị lộ.

Nếu dùng Nginx/CDN trực tiếp phục vụ assets, cấu hình của Spring Boot **không điều khiển được file root của Nginx/CDN**. Phải kiểm toán `root`/`alias`, redirect, rewrite và quyền file ở web server đó theo cơ chế riêng.

## 10. Checklist review trước khi triển khai

| Câu hỏi | Kỳ vọng |
| --- | --- |
| URL public là gì? | Một prefix rõ như `/assets/**`, không vô tình phủ toàn bộ app |
| Thư mục public là gì? | `classpath:/public-assets/` hoặc root khác chỉ chứa file được phê duyệt |
| Có default static handler ngoài ý muốn? | Tắt hoặc cấu hình chặt; xét cả ServletContext root và proxy |
| Có endpoint tự nối path client vào filesystem? | Loại bỏ hoặc thay bằng ID logic + authorization + canonical containment |
| Có symlink/mount/file upload trong vùng public? | Không có đường vượt root; kiểm soát quyền ghi và loại nội dung |
| Có file secret, backup, source map nhạy cảm trong artifact public? | Không; có bước rà soát đóng gói |
| Tầng URL decoding có thống nhất? | Đã kiểm thử qua proxy/container production |
| Có bản vá Spring/servlet container liên quan? | Đã kiểm tra advisory và phiên bản chạy thực |
| Tài nguyên cá nhân dùng static `permitAll`? | Không; phải là endpoint có phân quyền |
| Test khẳng định đúng boundary? | Public file -> 200; file thực ngoài root -> không truy cập được qua nhiều URL |

## 11. Những hiểu lầm thường gặp

**“Chỉ cần lọc `../` bằng `replace` là xong.”** Sai. Có encoding, backslash, absolute path, symlink và sự khác biệt giữa các tầng xử lý URL.

**“`Path.normalize()` tự chặn traversal.”** Sai. Nó chuẩn hóa đường dẫn, **không kiểm tra** đường dẫn đã rời thư mục được phép. Cần kiểm tra containment trên đối tượng `Path` tin cậy và cân nhắc symlink/TOCTOU.

**“Dùng `String.startsWith(root)` là đủ.”** Sai. `/srv/app/public-bak` vẫn có thể bắt đầu bằng chuỗi `/srv/app/public`. Cần `Path.startsWith(Path)` trên các path đã xử lý phù hợp.

**“URL `/assets/**` an toàn dù location là thư mục gốc.”** Sai. URL pattern hẹp không sửa được một location chứa quá nhiều file.

**“File dưới classpath luôn là public.”** Sai. File chỉ public khi có mapping/handler khác cho phép truy cập. Nhưng đừng dựa vào giả định đó để đóng gói secret trong JAR.

**“Thêm Spring Security `permitAll`/`authenticated` là đủ chống path traversal.”** Sai. Authorization theo URL và file resource containment là **hai lớp kiểm soát độc lập**.

**“Một test với `../` trả 404 chứng minh không thể traversal.”** Sai. Cần file canary tồn tại ngoài vùng public, kiểm thử nhiều biến thể và chạy qua đúng HTTP stack/proxy.

## 12. Tự kiểm tra

1. Ứng dụng chỉ map `/assets/**` tới `classpath:/public-assets/`. File `src/main/resources/internal-demo/marker.txt` có được phục vụ tự động ở `/assets/../internal-demo/marker.txt` không? **Không được phép**; nếu có thì đó là lỗi bảo mật.
2. Vì sao không để người dùng truyền `/download?path=../../...` dù có Spring Security? **Vì xác thực không bảo đảm đường dẫn được yêu cầu thuộc phạm vi file người dùng được quyền đọc.**
3. Vì sao nên đặt `spring.web.resources.add-mappings=false` trong ví dụ mapping nghiêm ngặt? **Để tắt các static mappings mặc định do Boot tự cấu hình và chỉ dùng handler tùy chỉnh đã khai báo**, cùng với kiểm tra các route khác.
4. Hai thư mục `/srv/app/public` và `/srv/app/public-bak` có thể được phân biệt an toàn bằng `String.startsWith` không? **Không**; cần so sánh thành phần path và xử lý symlink.
5. Khi file nằm trong root public nhưng chứa token thật, `PathResourceResolver` có tự chặn nội dung nhạy cảm không? **Không**; mọi file trong vùng public phải được xem là có thể công khai.
6. Vì sao phải nâng cấp Spring Framework dù handler chuẩn đã kiểm tra location? **Vì từng có CVE path traversal liên quan một số cấu hình static resources**, chẳng hạn CVE-2024-38816 và CVE-2026-41843.
7. Khi request qua CDN và reverse proxy trả về 400 thay vì 404 cho URL mã hóa lạ, có nhất thiết là lỗi không? **Không**; mục tiêu bảo mật là không trả resource nằm ngoài root, còn status cụ thể phụ thuộc tầng từ chối.

## 13. Tài liệu chính thức để đối chiếu

- Spring Boot, *Servlet Web Applications – Static Content*: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Framework, *Spring MVC Static Resources*: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html
- Spring Boot, *Reactive Web Applications – Static Content*: https://docs.spring.io/spring-boot/reference/web/reactive.html
- Spring Framework, *WebFlux Config – Static Resources*: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Security, *Authorization*: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- OWASP, *Path Traversal*: https://owasp.org/www-community/attacks/Path_Traversal
- Spring Security Advisory *CVE-2024-38816*: https://spring.io/security/cve-2024-38816/
- Spring Security Advisory *CVE-2026-41843*: https://spring.io/security/cve-2026-41843/

**Kết luận:** Hãy **công bố theo danh sách location do server kiểm soát**, dùng resource handler chuẩn của Spring thay vì tự ghép đường dẫn từ request, đặt public assets trong thư mục riêng, tắt các mapping mặc định không cần thiết, và kiểm thử rằng file thật nằm ngoài vùng public không bao giờ được trả về. Luôn duy trì bản vá bảo mật, giới hạn quyền file và xử lý tài liệu cần phân quyền bằng endpoint riêng.