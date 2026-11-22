# Spring MVC — Đường dẫn công khai khi ứng dụng nằm sau reverse proxy

## 1. Bài toán

Khi triển khai Spring Boot trên server hoặc container, ứng dụng thường không trực tiếp tiếp nhận URL công khai của client. HTTPS có thể kết thúc ở reverse proxy/API gateway, còn request tới Spring MVC đi qua HTTP và một đường dẫn nội bộ.

~~~text
Browser:
  https://learn.example.com/java/api/v1/books/42
            |
            v
Reverse proxy:
  TLS termination, public host, strip prefix /java
            |
            v
Spring Boot:
  http://backend:8080/api/v1/books/42
~~~

Nếu backend tự lấy scheme, host, port và path nội bộ rồi tạo liên kết, response có thể sai:

~~~http
HTTP/1.1 201 Created
Location: http://backend:8080/api/v1/books/42
~~~

URL public đúng phải là:

~~~http
HTTP/1.1 201 Created
Location: https://learn.example.com/java/api/v1/books/42
~~~

Điều này ảnh hưởng tới `201 Created + Location`, redirect `302/303`, liên kết HATEOAS, Swagger/OpenAPI server URL, OAuth2 callback, password reset links và các URL gửi qua email.

**Mục tiêu:** hiểu và kiểm soát public URI khi có reverse proxy; xử lý forwarded headers an toàn; phân biệt proxy prefix với Servlet context path/API version; sử dụng Spring Boot `server.forward-headers-strategy` và `ServletUriComponentsBuilder`; cấu hình Nginx; kiểm thử HTTP response, path rewrite và chống giả mạo host.

Phạm vi: Spring MVC Servlet stack, Java 17+, Spring Boot 3.5.0 và Spring Framework 6.2. WebFlux sử dụng cơ chế khác là `ForwardedHeaderTransformer`.

## 2. Public URL, internal URL và đường dẫn trong ứng dụng

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Public scheme | `https` | Giao thức browser thấy |
| Public host | `learn.example.com` | Tên miền được DNS/TLS/cổng public phục vụ |
| Public port | `443` | HTTPS effective port, thường được lược trong URL |
| Public mount prefix | `/java` | Nhánh URL mà proxy dùng để mount ứng dụng |
| API version path | `/api/v1` | Hợp đồng/version của chính API |
| Resource path | `/books/42` | Tài nguyên cụ thể |
| Internal origin | `http://backend:8080` | Proxy gọi backend |
| Spring handler path | `/api/v1/books/{id}` | `@GetMapping` thực tế trong Servlet app |
| Servlet context path | `server.servlet.context-path` | Prefix riêng của Servlet container, có thể rỗng |

**Không đồng nhất** `/java` với `/api/v1`. Proxy prefix là đặc tính topology triển khai; API version là phần của contract client. Nếu mount app từ `/java` sang `/learn`, số phiên bản `v1` có thể không đổi, nhưng public URLs trong bookmarks và SDKs vẫn bị ảnh hưởng.

### 2.1. Vì sao URL bị sai?

Với proxy strip prefix:

~~~text
GET https://learn.example.com/java/api/v1/books/42
 -> proxy_pass
GET http://backend:8080/api/v1/books/42
~~~

Backend có thể thấy:

~~~text
request.getScheme()      = "http"
request.getServerName()  = "backend"
request.getServerPort()  = 8080
request.getContextPath() = ""
request.getRequestURI()  = "/api/v1/books/42"
~~~

Đây là dữ liệu đúng từ góc nhìn mạng nội bộ, nhưng **không phải canonical address để trả cho client**.

Một API trong production cần giao thức tin cậy để truyền public scheme, host, port và path prefix từ proxy vào Spring.

## 3. Forwarded và X-Forwarded-* là gì?

### 3.1. Header chuẩn Forwarded (RFC 7239)

Header RFC 7239 có cú pháp như:

~~~http
Forwarded: for=192.0.2.10;proto=https;host=learn.example.com
~~~

Nó mô tả thông tin request theo các proxy hops, có thể chứa nhiều elements. RFC này không định nghĩa phổ quát một trường path prefix thay thế `X-Forwarded-Prefix`.

### 3.2. Các headers thông dụng

| Header | Giá trị ví dụ | Tác dụng |
| --- | --- | --- |
| `X-Forwarded-Proto` | `https` | Scheme public của client |
| `X-Forwarded-Host` | `learn.example.com` | Host public |
| `X-Forwarded-Port` | `443` | Port public |
| `X-Forwarded-Prefix` | `/java` | Mount prefix public bị proxy rewrite |
| `X-Forwarded-For` | `192.0.2.10` | IP chain phía client/proxy |
| `X-Forwarded-Ssl` | `on` | Một quy ước legacy về TLS |

Ví dụ backend request:

~~~http
GET /api/v1/books/42 HTTP/1.1
Host: backend:8080
X-Forwarded-Proto: https
X-Forwarded-Host: learn.example.com
X-Forwarded-Port: 443
X-Forwarded-Prefix: /java
~~~

Nếu Spring xử lý đúng bộ headers **được tạo từ proxy tin cậy**, nó có thể tạo public URL hợp lệ mặc dù upstream trực tiếp dùng HTTP nội bộ.

### 3.3. Headers không tự đáng tin

Một client có thể gửi:

~~~http
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: https
X-Forwarded-Prefix: /evil
~~~

Spring app **không thể tự biết** những headers ấy do reverse proxy tin cậy set hay do attacker gửi. Nếu client có quyền truy cập trực tiếp tới backend, việc tin các giá trị này có thể gây:

- Host-header injection và links trỏ tới domain attacker.
- Open redirect qua Location.
- Password-reset email link poisoning.
- OAuth/OIDC redirect_uri bị sửa.
- Log spoofing hoặc phân tích sai IP client.
- Cache poisoning khi proxy/cache dùng sai Host.

**Nguyên tắc:** edge proxy phải **xóa** forwarded headers từ Internet và **ghi đè** canonical values đáng tin; backend chỉ chấp nhận network traffic từ proxy hoặc trusted upstream.

## 4. server.forward-headers-strategy trong Spring Boot

Spring Boot 3.5 hỗ trợ:

~~~properties
server.forward-headers-strategy=framework
~~~

| Giá trị | Nguồn xử lý | Lưu ý |
| --- | --- | --- |
| `none` | Không tự bật forwarded-header processing qua Boot | Hợp khi app không có proxy tin cậy hoặc public URL dùng config riêng |
| `native` | Container xử lý natively (Tomcat/Jetty) | Có thể đủ với X-Forwarded-For/Proto tùy container |
| `framework` | Spring Framework, với Servlet là forwarded-header filter support | Thường phù hợp khi cần host/port/proto và `X-Forwarded-Prefix` |

Tài liệu Spring Boot nói với một proxy đưa `X-Forwarded-For` và `X-Forwarded-Proto`, chế độ `NATIVE` có thể đủ. Nếu native implementation không xử lý tất cả đặc điểm cần dùng, nhất là path prefix, chế độ `FRAMEWORK` cho Spring MVC thường được dùng.

### 4.1. Mặc định thay đổi theo platform

Với một số cloud environments được Spring Boot nhận diện, giá trị mặc định có thể là `NATIVE`, còn môi trường khác là `NONE`. Nên xác định tường minh trong production profile:

~~~properties
# application-prod.properties
server.forward-headers-strategy=framework
~~~

Đừng bật khi client Internet gọi trực tiếp backend có thể tự gửi arbitrary Forwarded headers. **Property này không thay proxy trust policy.**

### 4.2. ForwardedHeaderFilter

Trong Spring MVC, `org.springframework.web.filter.ForwardedHeaderFilter` là Servlet filter xử lý `Forwarded` và `X-Forwarded-*` để downstream nhìn request từ góc nhìn client. Nó wrap request/response, dùng forwarded metadata, loại ảnh hưởng tiếp tục của raw headers và cần chạy đủ sớm trước các filters/handlers khác dựa vào URI.

Nếu Boot đã được cấu hình:

~~~properties
server.forward-headers-strategy=framework
~~~

thì không cần tự tạo thêm một bean `ForwardedHeaderFilter` giống nhau. Tránh native + framework + manual filter cùng xử lý vô tình.

Filter có `setRemoveOnly(true)` nếu chỉ muốn **loại bỏ** headers chưa đáng tin mà không sử dụng chúng. Mode removeOnly không giúp khôi phục public scheme/host/prefix — dùng khi có canonical URL config khác hoặc muốn harden.

### 4.3. Khi async hoặc error dispatch

Với MVC async `Callable`/`DeferredResult`, Servlet có REQUEST và ASYNC dispatch; lỗi có thể qua ERROR dispatch. Forwarded filter khi tự đăng ký cần đúng ordering/dispatcher types, để request/response nhất quán. Trong Boot nên xác minh registration thực tế khi dùng custom filter registration; không chỉ thử một GET 200 đồng bộ.

### 4.4. Tomcat TLS termination

Spring Boot 3.5 hướng dẫn trong trường hợp Tomcat đứng sau proxy terminate SSL có thể cần:

~~~properties
server.tomcat.redirect-context-root=false
~~~

để X-Forwarded-Proto có thể được xử lý trước một số redirects ở context root. Chỉ dùng theo topology/version cụ thể và test; không mặc định thêm để chữa mọi redirect loop.

## 5. X-Forwarded-Prefix và ba kiểu rewrite

### 5.1. Strip prefix

~~~text
Public : https://learn.example.com/java/api/v1/books/42
Backend: http://backend:8080/api/v1/books/42
X-Forwarded-Prefix: /java
~~~

Backend route vẫn là:

~~~java
@GetMapping("/api/v1/books/{id}")
~~~

Nếu không xử lý prefix, URI builder có thể trả `https://learn.example.com/api/v1/books/42`, thiếu `/java`.

### 5.2. Giữ prefix

~~~text
Public : https://learn.example.com/java/api/v1/books/42
Backend: http://backend:8080/java/api/v1/books/42
~~~

Có thể dùng `server.servlet.context-path=/java` hoặc route/mapping chứa prefix nếu đó là thiết kế. Khi đã giữ prefix phía backend, không thêm `/java` lần thứ hai bằng cả request builder và custom code.

### 5.3. Thay context path thay vì cộng chuỗi

Spring Framework docs nêu X-Forwarded-Prefix có thể **override**, **remove** hoặc **prepend** prefix gốc trong các topology khác nhau:

| Public | Internal | Ý nghĩa |
| --- | --- | --- |
| `https://example.com/api/x` | `http://backend:8080/app1/x` | Prefix public `/api` thay cho `/app1` |
| `https://app1.example.com/x` | `http://backend:8080/app1/x` | Public prefix rỗng thay internal `/app1` |
| `https://example.com/api/app1/x` | `http://backend:8080/app1/x` | Public prefix `/api/app1` |

Không dùng quy tắc tự chế `contextPath + forwardedPrefix` cho mọi deployment: có thể thành `/java/java` hoặc bỏ prefix.

### 5.4. Quy tắc ownership

Chọn **một nơi** quản lý mỗi phần:

- Gateway quyết định public host, TLS scheme, public port, mount prefix và rewrite.
- Servlet container/Spring biết internal context path và handler mappings.
- URI builder dựa vào request đã chuẩn hóa.
- API versioning là phần contract đã thiết kế riêng.

Nếu ingress và edge gateway đều set X-Forwarded-Prefix, cần thống nhất hop nào giữ final canonical prefix và ai xóa metadata cũ.

## 6. ServletUriComponentsBuilder tạo public URL

Import:

~~~java
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;
~~~

Khi có request Servlet đã xử lý forwarded headers:

~~~java
URI location = ServletUriComponentsBuilder
        .fromCurrentContextPath()
        .path("/api/v1/books/{id}")
        .buildAndExpand(book.id())
        .toUri();

return ResponseEntity.created(location).build();
~~~

**Không** tự đọc raw X-Forwarded-Host/Proto rồi nối chuỗi. Spring docs nêu từ Framework 5.1, `ServletUriComponentsBuilder` không tự parse forwarded headers; ứng dụng cần `ForwardedHeaderFilter` hoặc cơ chế tương đương ở container xử lý trước.

### 6.1. Các factory methods

| API | Nội dung | Mục đích |
| --- | --- | --- |
| `fromCurrentContextPath()` | Scheme/host/port và context path | Tạo một URI khác cùng ứng dụng |
| `fromCurrentRequestUri()` | Địa chỉ + path request hiện tại, không query | Tạo self link |
| `fromCurrentRequest()` | Như request hiện tại, bao gồm query | Tạo self URI có query khi thực sự cần |
| `fromContextPath(request)` | Cấp HttpServletRequest tường minh | Khi không dùng current request holder trực tiếp |

Với POST `/api/v1/books` tạo GET `/api/v1/books/42`, `fromCurrentContextPath().path(...)` dễ hiểu hơn vì không phụ thuộc path của POST.

### 6.2. URI template và encoding

~~~java
URI uri = ServletUriComponentsBuilder
        .fromCurrentContextPath()
        .path("/api/documents/{name}")
        .encode()
        .buildAndExpand(documentName)
        .toUri();
~~~

Đoạn code trên là fragment; `documentName` cần hợp đồng và validation. Encode giúp tránh tự ghép path sai, nhưng không tự giải quyết quyền truy cập hoặc path traversal nếu logic cho phép tên tài liệu bất thường.

### 6.3. 201 Location và redirect

HTTP API tạo resource thường trả:

~~~http
HTTP/1.1 201 Created
Location: https://learn.example.com/java/api/v1/books/42
~~~

Trong MVC view controller:

~~~java
@PostMapping("/checkout")
public String complete(RedirectAttributes attrs) {
    long id = createOrder(); // Fragment minh họa service.
    attrs.addAttribute("id", id);
    return "redirect:/orders/{id}";
}
~~~

Các redirect `302/303`, JSON self links và HATEOAS cũng phải có URL public đúng, không lộ port 8080 hay prefix nội bộ. Header Location có thể là relative URI reference, nhưng **relative path vẫn phải giữ đúng public mount prefix**.

## 7. Reverse proxy Nginx minh họa

Public `https://learn.example.com/java/...`, Spring backend `http://127.0.0.1:8080/...`. Nginx strip `/java/` rồi gửi backend:

~~~nginx
server {
    listen 443 ssl;
    server_name learn.example.com;

    # TLS certificate, key và các security settings phải cấu hình riêng.

    location /java/ {
        proxy_pass http://127.0.0.1:8080/;

        # Edge phải loại Forwarded do client gửi.
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-Ssl "";

        # Canonical metadata, không tin arbitrary client Host.
        proxy_set_header Host learn.example.com;
        proxy_set_header X-Forwarded-Host learn.example.com;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-Prefix /java;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
~~~

**Đây là fragment thiết kế**, chưa đủ để deploy: cần TLS certificates, default-host rejection, firewall/private backend, redirects phù hợp, timeout/headers, HSTS theo policy và xử lý URL `/java` không có slash cuối. Nếu Nginx nằm sau CDN khác, `$remote_addr` có thể là IP CDN; thiết kế real-IP trusted chain riêng, không tự tin X-Forwarded-For do client thêm.

### 7.1. Chú ý trailing slash của proxy_pass

~~~nginx
location /java/ {
    proxy_pass http://127.0.0.1:8080/;
}
~~~

Trong prefix location bình thường, URI `/` ở cuối `proxy_pass` thay phần location match, dẫn tới:

~~~text
/java/api/v1/books/42 -> /api/v1/books/42
~~~

Không có URI ở cuối:

~~~nginx
location /java/ {
    proxy_pass http://127.0.0.1:8080;
}
~~~

có thể giữ:

~~~text
/java/api/v1/books/42 -> /java/api/v1/books/42
~~~

Với controller mapping `/api/v1/books/{id}`, trường hợp giữ prefix có thể 404. Đừng sửa mapping Java trước khi biết proxy thực tế có strip hay không.

### 7.2. Host cố định và forwarded-for

Trong Nginx, dùng canonical `learn.example.com` trong Host/X-Forwarded-Host cho ví dụ một domain giúp tránh proxy phản chiếu một host bất kỳ. Cần xử lý/deny unknown Host tại virtual host/default server. Nếu hệ thống multi-domain, phải có domain allowlist và cơ chế xác định canonical host đáng tin.

Dùng `X-Forwarded-For: $remote_addr` ở edge là một cách overwrite, tránh chuyển nguyên danh sách có thể bị client spoof. Với chain nhiều proxies, cần thiết kế trusted proxy hops và client-IP extraction cẩn thận; đừng dùng IP header làm authentication.

## 8. Java 17 Spring Boot 3.5 Maven demo

Demo có ba endpoints:

- `GET /api/v1/self` — trả public URL hiện tại.
- `POST /api/v1/books` — tạo resource và trả 201 Location.
- `GET /api/v1/books/{id}` — lấy dữ liệu.

Khi proxy strip `/java`, Spring mappings **không chứa** `/java`. Boot tự cấu hình forwarding qua FRAMEWORK.

### 8.1. Cấu trúc

~~~text
public-url-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/PublicUrlApplication.java
    │   └── resources/application.properties
    └── test/java/demo/PublicUrlTest.java
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>public-url-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

### 8.3. application.properties

~~~properties
server.port=8080
server.forward-headers-strategy=framework

# Proxy sở hữu /java; không đồng thời đặt context-path=/java.
~~~

**Không sử dụng cấu hình này cho backend public không có trusted proxy**. Backend phải được network-restricted và edge phải strip/overwrite forwarded headers trước.

### 8.4. PublicUrlApplication.java

Lưu **toàn bộ Java** vào `src/main/java/demo/PublicUrlApplication.java`. Một top-level public class, các types khác package-private.

~~~java
package demo;

import java.net.URI;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@SpringBootApplication
public class PublicUrlApplication {
    public static void main(String[] args) {
        SpringApplication.run(PublicUrlApplication.class, args);
    }
}

record NewBook(String title) {}
record Book(long id, String title) {}

@Service
class BookService {
    private final AtomicLong ids = new AtomicLong(40);
    private final Map<Long, Book> books = new ConcurrentHashMap<>();

    Book create(String title) {
        if (title == null || title.isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Title required");
        }
        long id = ids.incrementAndGet();
        Book book = new Book(id, title);
        books.put(id, book);
        return book;
    }

    Book find(long id) {
        Book book = books.get(id);
        if (book == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Book not found");
        }
        return book;
    }
}

@RestController
@RequestMapping("/api/v1")
class BookController {
    private final BookService service;

    BookController(BookService service) {
        this.service = service;
    }

    @GetMapping(path = "/self",
                produces = MediaType.APPLICATION_JSON_VALUE)
    Map<String, String> self() {
        URI publicUri = ServletUriComponentsBuilder
                .fromCurrentRequestUri()
                .build()
                .toUri();
        return Map.of("publicUrl", publicUri.toString());
    }

    @PostMapping(path = "/books",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<Void> create(@RequestBody NewBook input) {
        Book book = service.create(input.title());
        URI location = ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/api/v1/books/{id}")
                .buildAndExpand(book.id())
                .toUri();
        return ResponseEntity.created(location).build();
    }

    @GetMapping(path = "/books/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    Book detail(@PathVariable long id) {
        return service.find(id);
    }
}
~~~

Application không dùng raw Forwarded headers trong controller. Dữ liệu lưu trong RAM để minh họa, không thay database/transactions/security.

### 8.5. Chạy backend và proxy

Từ thư mục Maven:

~~~bash
mvn spring-boot:run
~~~

Sau khi proxy/Nginx public URL đã hoạt động:

~~~bash
curl -i 'https://learn.example.com/java/api/v1/self'
~~~

Body mong đợi tương đương:

~~~json
{"publicUrl":"https://learn.example.com/java/api/v1/self"}
~~~

Tạo resource:

~~~bash
curl -i -X POST \
  'https://learn.example.com/java/api/v1/books' \
  -H 'Content-Type: application/json' \
  --data '{"title":"Spring MVC"}'
~~~

Với lần tạo đầu sau khi chạy app, response có thể là:

~~~http
HTTP/1.1 201 Created
Location: https://learn.example.com/java/api/v1/books/41
~~~

Các lần sau ID tăng; đừng hardcode 41 trong test. Browser/client GET Location để lấy resource.

### 8.6. MockMvc tests

Tạo `src/test/java/demo/PublicUrlTest.java`:

~~~java
package demo;

import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PublicUrlTest {
    @Autowired MockMvc mvc;

    @Test
    void selfLinkUsesPublicSchemeHostAndPrefix() throws Exception {
        mvc.perform(get("/api/v1/self")
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Host", "learn.example.com")
                .header("X-Forwarded-Port", "443")
                .header("X-Forwarded-Prefix", "/java"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.publicUrl").value(
                    "https://learn.example.com/java/api/v1/self"));
    }

    @Test
    void locationContainsPublicPrefixExactlyOnce() throws Exception {
        MvcResult result = mvc.perform(post("/api/v1/books")
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Host", "learn.example.com")
                .header("X-Forwarded-Port", "443")
                .header("X-Forwarded-Prefix", "/java")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Book\"}"))
            .andExpect(status().isCreated())
            .andReturn();

        String location = result.getResponse()
                .getHeader(HttpHeaders.LOCATION);
        assertNotNull(location);

        URI uri = URI.create(location);
        assertEquals("https", uri.getScheme());
        assertEquals("learn.example.com", uri.getHost());
        assertEquals(-1, uri.getPort());
        assertTrue(uri.getPath().matches(
                "/java/api/v1/books/[0-9]+"));
    }

    @Test
    void internalUriWithoutForwardedHeaders() throws Exception {
        mvc.perform(get("/api/v1/self")
                .with(request -> {
                    request.setScheme("http");
                    request.setServerName("localhost");
                    request.setServerPort(8080);
                    return request;
                }))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.publicUrl").value(
                    "http://localhost:8080/api/v1/self"));
    }

    @Test
    void invalidInputReturns400() throws Exception {
        mvc.perform(post("/api/v1/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\" \"}"))
            .andExpect(status().isBadRequest());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

MockMvc chỉ kiểm tra cách Spring xử lý metadata khi **được cung cấp headers mô phỏng proxy**. Nó **không xác minh nguồn headers đáng tin**. Phải test thực tế rằng Internet client không thể truy cập backend trực tiếp hoặc spoof header qua edge.

## 9. Link khi không có HTTP request

Một số nhiệm vụ không chạy trong Servlet request thread:

- Background jobs/scheduled tasks.
- Email xác nhận đăng ký, reset password.
- Message queue consumers.
- Webhook callback registration.
- Sitemap/SEO canonical links.
- OAuth callback URL tĩnh.

Không thể dựa vào `ServletUriComponentsBuilder.fromCurrentContextPath()` nếu không có request context. Hãy dùng cấu hình **public base URL canonical**:

~~~properties
app.public-base-url=https://learn.example.com/java
~~~

Trong Spring bean, ví dụ fragment:

~~~java
@Value("${app.public-base-url}")
private String publicBaseUrl;

URI uri = UriComponentsBuilder
        .fromUriString(publicBaseUrl)
        .path("/api/v1/books/{id}")
        .buildAndExpand(bookId)
        .toUri();
~~~

Cần imports `org.springframework.beans.factory.annotation.Value`, `org.springframework.web.util.UriComponentsBuilder`, `java.net.URI`. Các biến `bookId` và publicBaseUrl có hợp đồng trusted. Kiểm tra trailing slash/canonicalization của property để không sinh `/java//api`.

Với SaaS đa tenant, lấy canonical host từ tenant config được xác thực/allowlist, không đọc raw Host hay X-Forwarded-Host từ request bất kỳ để tạo email reset link.

## 10. Hệ quả với Spring Security và OAuth2

### 10.1. Redirect loop HTTP/HTTPS

Nếu client đã gọi HTTPS nhưng Spring backend nhận HTTP, cấu hình yêu cầu secure channel có thể liên tục chuyển hướng:

~~~text
Browser HTTPS -> Proxy HTTP -> App sees HTTP
App redirects to HTTPS -> Browser HTTPS -> Proxy HTTP -> ...
~~~

Cần sửa trusted X-Forwarded-Proto/Forwarded proto và Spring forwarding strategy, phối hợp ingress HTTPS redirect và Security transport policies. Không tắt TLS requirement chỉ để bỏ loop.

### 10.2. OAuth2 redirect_uri

Identity provider đăng ký:

~~~text
https://learn.example.com/java/login/oauth2/code/provider
~~~

Nếu Spring tạo:

~~~text
http://backend:8080/login/oauth2/code/provider
~~~

thường bị `redirect_uri_mismatch`. Kiểm trusted forwarded proto/host/prefix và provider registration, rồi test browser login flow thực tế.

### 10.3. Cookies

Public HTTPS sau proxy có thể ảnh hưởng `Secure`, `SameSite`, `HttpOnly` và `Path` của cookies. Nếu public app mount `/java`, cookie Path cần được chọn có chủ đích, không vô tình áp theo upstream prefix sai. Không giải quyết bằng cách tắt CSRF/cookie security.

## 11. Hệ quả với API versioning và HATEOAS

Một API có thể phát:

~~~json
{
  "id": 42,
  "_links": {
    "self": {
      "href": "https://learn.example.com/java/api/v1/books/42"
    }
  }
}
~~~

Đường dẫn HATEOAS đúng phải tương ứng với Location của cùng resource.

Nếu đổi deployment backend từ `backend-a:8080` sang `backend-b:9090`, public API vẫn giữ nguyên; đó là mục tiêu của reverse proxy. Nhưng nếu đổi public prefix từ `/java` sang `/learn`, URLs cũ trong emails/SDK/bookmarks có thể hỏng dù vẫn dùng `/api/v1`. Cân nhắc alias/redirect migration, tài liệu deprecation, OpenAPI servers và cache/CDN invalidation.

**Không dùng X-Forwarded-Prefix để thay thế version URI**. Proxy routing và API version lifecycle là hai quyết định độc lập.

## 12. Debug theo triệu chứng

| Triệu chứng | Khả năng thường gặp | Cách xử lý |
| --- | --- | --- |
| Location vẫn là `http://...` | Chưa xử lý trusted proto hoặc proxy set sai | Kiểm X-Forwarded-Proto và strategy |
| Location có `backend:8080` | Host/port forwarded bị mất hoặc ignored | Kiểm proxy headers, native/framework |
| Public Location thiếu `/java` | Proxy strip prefix nhưng thiếu X-Forwarded-Prefix | Bổ sung prefix có nguồn tin cậy, dùng framework |
| Location có `/java/java` | Proxy + Servlet/app cùng thêm prefix | Quy định một owner của prefix |
| Internal URL 200 nhưng public URL 404 | URI rewrite sai (proxy_pass slash) | Đối chiếu actual upstream request URI |
| Login redirect loop | Scheme app thấy HTTP dù public HTTPS | Sửa proxy/TLS forwarding/Security |
| OAuth redirect_uri mismatch | Public callback sai scheme/host/prefix | Kiểm IdP config và forwarding |
| Swagger UI gọi backend:8080 | OpenAPI servers dùng internal URL | Cấu hình server URI public |
| Client thay X-Forwarded-Host khiến Location đổi | Trust boundary hỏng | Edge strip/overwrite headers, backend private |
| Cookie login không thành công | Cookie Path, Secure hoặc SameSite | Browser DevTools/proxy scheme |
| X-Forwarded-For hiển thị IP giả | Proxy tin client-supplied XFF | Trusted hop policy, overwrite at edge |
| Async/error redirects sai nhưng GET đúng | Dispatcher type/filter order khác | Kiểm forwarding registration trên ASYNC/ERROR |

### 12.1. Phương pháp debug

1. Ghi lại **public URL chính xác** ở browser.
2. Ghi lại **URI backend thực sự nhận** sau gateway rewrite.
3. Kiểm public scheme, host, port và prefix được trusted proxy gắn.
4. Xác định Boot strategy và filter/container forwarding behavior.
5. Kiểm controller mapping/context path có chứa prefix không.
6. Dùng curl xem **201 Location, 302/303 Location và JSON self links**.
7. Test spoofed Host/X-Forwarded headers qua edge.
8. Kiểm TLS, OAuth, Security, cookie policies và CORS/mixed content.
9. Nếu có CDN/service mesh, xác định một hop làm canonical authority.
10. Test lại từ external staging URL, không kết luận chỉ từ MockMvc.

## 13. Những lỗi phổ biến

- Hardcode `localhost:8080`, backend host hoặc port vào JSON/Location.
- Tạo URL bằng string concatenation từ raw Forwarded headers.
- Bật forwarded-header support khi backend direct port còn public.
- Proxy không strip headers client gửi.
- Chỉ xử lý X-Forwarded-Proto mà bỏ Host/Port/Prefix.
- Chọn NATIVE rồi giả định container xử lý X-Forwarded-Prefix giống Framework.
- Đăng ký trùng ForwardedHeaderFilter và native handling.
- Đặt `server.servlet.context-path=/java` trong khi proxy đã strip và gửi X-Forwarded-Prefix.
- Quên trailing slash Nginx proxy_pass làm backend 404.
- Gắn API version vào X-Forwarded-Prefix khiến public contract sai.
- Tạo absolute links trong scheduled job mà không có Servlet request.
- Sử dụng Host header làm nguồn sinh password-reset link.
- Cho rằng X-Forwarded-For đã được authenticate.
- Chỉ kiểm response body mà bỏ Location và HATEOAS.
- Không test 401/403/500, ASYNC/ERROR dispatch và proxy-generated errors.
- Không kiểm Swagger/OAuth callback và cookie Path.
- Đổi public prefix mà không có kế hoạch tương thích clients.

## 14. Checklist triển khai

- [ ] Public origin và prefix đã được xác định rõ theo environment.
- [ ] Proxy rewrite path được mô tả chính xác, không dựa vào phỏng đoán.
- [ ] Backend private chỉ nhận traffic từ trusted upstream.
- [ ] Edge xóa mọi `Forwarded` và `X-Forwarded-*` từ client trước khi set canonical headers.
- [ ] Public Host/domain được validate hoặc cố định.
- [ ] Boot forwarding strategy được chọn tường minh, không xử lý kép.
- [ ] Servlet context path, X-Forwarded-Prefix và controller route không thêm trùng prefix.
- [ ] 201 Location và 3xx redirects chứa đúng HTTPS host/prefix.
- [ ] Self links, OpenAPI servers và OAuth callbacks đúng public URL.
- [ ] Cookie Secure/SameSite/Path và Spring Security không sai dưới TLS termination.
- [ ] Client không thể spoof forwarded host/proto/prefix qua public proxy.
- [ ] Email/webhook/job URLs dùng trusted canonical base config.
- [ ] Integration tests qua proxy thật bao gồm lỗi, async, redirects và health checks.
- [ ] Version API path độc lập với proxy mount prefix; có migration nếu đổi public mount.

## 15. Bài tập

**Bài 1.** Browser gọi `https://example.com/java/api/v1/books/42`, proxy gọi `http://backend:8080/api/v1/books/42`. Xác định public origin, mount prefix, API version path và forwarded headers.

**Bài 2.** Một POST trả `Location: https://example.com/api/v1/books/42` nhưng phải có `/java`. Nêu cách kiểm Nginx rewrite, X-Forwarded-Prefix, Boot strategy và Servlet context path.

**Bài 3.** Giải thích khác nhau giữa `proxy_pass http://backend:8080/;` và `proxy_pass http://backend:8080;` trong `location /java/`.

**Bài 4.** Nếu client gửi `X-Forwarded-Host: attacker.example`, edge cần làm gì? Đưa ra integration test chống URL poisoning và direct backend access.

**Bài 5.** Viết `ResponseEntity.created(location)` với `ServletUriComponentsBuilder.fromCurrentContextPath()` cho resource ID mới. Dùng MockMvc để kiểm `https://example.com/java/api/v1/books/{id}`.

**Bài 6.** So sánh NATIVE và FRAMEWORK khi proxy chỉ gửi proto/for, và khi proxy còn strip public prefix.

**Bài 7.** Spring Security phát OAuth callback internal HTTP thay vì HTTPS public. Liệt kê những thành phần cấu hình cần kiểm.

**Bài 8.** Scheduled job gửi link reset-password nhưng không có request. Vì sao không dùng `fromCurrentContextPath()`? Thiết kế public-base-url an toàn.

**Bài 9.** Public prefix đổi `/java` thành `/learn`, API vẫn `/api/v1`. Giải thích tác động với SDK/bookmarks và cách giữ compatibility.

**Bài 10.** Có CDN → ingress → service mesh → Spring. Chỉ định hop xử lý canonical forwarded headers và chống duplicate headers/IP spoofing.

## 16. Ghi nhớ

- Public URL **không giống** internal upstream URL khi ứng dụng đứng sau proxy.
- Forwarded metadata giải thích scheme/host/port/prefix gốc; chúng chỉ đáng tin nếu proxy làm trust boundary.
- Spring Boot có `none`, `native` và `framework`; với Servlet MVC cần path prefix, FRAMEWORK thường là lựa chọn rõ.
- X-Forwarded-Prefix không phải API version và không nên được nối nhiều lần.
- ServletUriComponentsBuilder dùng request **đã được chuẩn hóa**; không tự tin raw X-Forwarded headers.
- Location, redirects, self links, Swagger/OpenAPI và OAuth2 callback phải là địa chỉ công khai chính xác.
- Khi không có HTTP request, dùng trusted canonical public-base-url.
- Bảo vệ backend direct access, strip spoofed forwarded headers và kiểm thử cả HTTP link correctness lẫn security.

## 17. Tài liệu tham khảo

- [Spring Boot 3.5 — Running Behind a Front-end Proxy](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html).
- [Spring Framework 6.2 — Forwarded Headers, Servlet Filters](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html).
- [Spring Framework 6.2 — URI Links](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-uri-building.html).
- [ServletUriComponentsBuilder API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/support/ServletUriComponentsBuilder.html).
- [ForwardedHeaderFilter API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/filter/ForwardedHeaderFilter.html).
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239).
- [NGINX proxy_pass](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass).
