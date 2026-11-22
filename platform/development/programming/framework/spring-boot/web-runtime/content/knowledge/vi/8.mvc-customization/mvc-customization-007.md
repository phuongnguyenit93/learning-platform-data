# PathPatternParser, mẫu đường dẫn và cách chọn chiến lược khớp URL trong Spring MVC

> **Phạm vi:** Spring Boot **3.5.x**, Spring Framework **6.2.x**, Java **17+**, ứng dụng **Spring MVC trên Servlet stack**. Tài liệu này giải thích `PathPatternParser`, cú pháp và giới hạn mẫu đường dẫn, mức độ ưu tiên giữa các mapping, so sánh `AntPathMatcher`, cách chọn chiến lược qua Spring Boot, tác động đến prefix/encoding/bảo mật, ví dụ Maven có thể chạy và kiểm thử HTTP thực. Phần cuối phân biệt rõ Spring WebFlux.

## 1. Khớp đường dẫn nằm ở đâu trong luồng Spring MVC?

Giả sử client yêu cầu:

~~~http
GET /api/catalog/featured HTTP/1.1
Host: localhost:8080
~~~

Ứng dụng có hai controller mapping:

~~~java
@GetMapping("/api/catalog/featured")
public String featured() { return "featured"; }

@GetMapping("/api/catalog/{slug}")
public String bySlug(@PathVariable String slug) {
    return slug;
}
~~~

Cả hai mẫu đều có thể phù hợp với path `/api/catalog/featured`. Spring MVC phải xác định **mapping cụ thể nhất** chứ không mặc định gọi method được khai báo trước trong source file.

Luồng rút gọn:

~~~text
HTTP client
     |
     v
Embedded Servlet container (Tomcat/Jetty/Undertow)
     |
     v
DispatcherServlet
     |
     v
RequestMappingHandlerMapping
     |
     +-- lấy đường dẫn cần match của request
     +-- kiểm tra điều kiện path, HTTP method, params, headers,
     |   consumes, produces...
     +-- so sánh độ cụ thể nếu nhiều mapping đều phù hợp
     |
     v
HandlerMethod
     |
     v
RequestMappingHandlerAdapter
     |
     v
Controller method -> response
~~~

`PathPatternParser` và `AntPathMatcher` liên quan đến **cách biểu diễn và khớp path**, không thay thế toàn bộ `HandlerMapping`. Một request còn phải phù hợp với các điều kiện khác như `GET`/`POST`, `consumes`, `produces` và header.

**Phân biệt bốn khái niệm:**

| Thành phần | Vai trò |
|---|---|
| `@GetMapping("/api/items/{id}")` | Chuỗi mẫu đường dẫn cùng các điều kiện request do lập trình viên khai báo |
| `PathPatternParser` | Biên dịch chuỗi pattern thành đối tượng `PathPattern` để match có cấu trúc |
| `RequestPath` / `PathContainer` | Biểu diễn đường dẫn request theo từng segment |
| `RequestMappingHandlerMapping` | Giữ tập mapping và lựa chọn handler thích hợp khi request đến |

Trong chế độ legacy, `AntPathMatcher` thực hiện so khớp chuỗi path; nó không tạo một `PathPattern` đã parse theo cùng mô hình.

## 2. Vì sao Spring Framework chuyển sang PathPatternParser?

Trước đây MVC thường sử dụng `AntPathMatcher`: lấy request path dưới dạng `String` và khớp với chuỗi pattern. Cách này linh hoạt nhưng có những thách thức liên quan mã hóa URL, các ký tự phân tách, xử lý matrix variables và hiệu năng khi phải phân tích lại nhiều mẫu.

`PathPatternParser` được giới thiệu cho Spring MVC từ Spring Framework 5.3 và trở thành **mặc định từ Spring Framework 6.0**. Spring Boot 3.5.x dựa trên Spring Framework 6.2.x, nên ứng dụng MVC thông thường sử dụng chiến lược này nếu không chủ động đổi cấu hình.

Cơ chế chính:

1. Khi đăng ký controller mapping, chuỗi pattern được parse thành `PathPattern`, biểu diễn các phần tử đường dẫn.
2. Khi nhận request, Spring phân tích path thành `RequestPath`/`PathContainer` với từng path segment.
3. `PathPattern` đối chiếu với từng segment thay vì chỉ giải mã toàn bộ URL thành một `String` rồi match.
4. Nếu nhiều mapping đáp ứng điều kiện, MVC dùng cơ chế so sánh độ cụ thể phù hợp với loại pattern.
5. Chọn `HandlerMethod` và gọi qua `RequestMappingHandlerAdapter`.

Phân tích từng segment giúp giữ ranh giới đường dẫn khi gặp ký tự mã hóa trong một segment, chẳng hạn dấu chấm phẩy hoặc dấu gạch chéo được percent-encode. Tuy nhiên **điều này không có nghĩa mọi encoded slash sẽ được mọi container, reverse proxy hoặc firewall chấp nhận**; tầng ngoài ứng dụng vẫn có quyền từ chối request.

Mô hình minh họa:

~~~text
Pattern:     /api/files/{name}
                  |      |
Parsed:      literal  capture one segment

Request:     /api/files/readme.txt
                  |      |
RequestPath: literal  "readme.txt"

Result: matches, name = "readme.txt"
~~~

`PathPatternParser` là thành phần dành cho xử lý đường dẫn web; không phải mọi chỗ dùng `AntPathMatcher` trong hệ sinh thái Spring đều bắt buộc chuyển sang parser này.

## 3. Cú pháp mẫu đường dẫn của PathPatternParser

Các ký hiệu thường dùng:

| Pattern | Ý nghĩa | Ví dụ match | Ví dụ không match / lưu ý |
|---|---|---|---|
| `/api/health` | Đường dẫn literal chính xác | `/api/health` | `/api/healthcheck` |
| `/api/items/{id}` | Bắt **một** path segment vào biến `id` | `/api/items/42` | `/api/items/42/details` |
| `/api/items/{id:[0-9]+}` | Biến kèm regex giới hạn từng segment | `/api/items/123` | `/api/items/abc` |
| `/assets/*.png` | `*`: 0 hoặc nhiều ký tự trong **một** segment | `/assets/logo.png` | `/assets/img/logo.png` |
| `/pages/t?st.html` | `?`: đúng **một ký tự** trong một segment | `/pages/test.html` | `/pages/toast.html` |
| `/assets/**` | `**`: 0 hoặc nhiều path segment **ở cuối** pattern | `/assets/img/a.png` | `/assets/**/tail` là cú pháp **không hợp lệ** |
| `/assets/{*path}` | Bắt **phần đường dẫn còn lại** vào biến `path` | `/assets/img/a.png` | `/{*path}/tail` không hợp lệ |
| `/v1/{type:[a-z]+}/info` | Biến ở giữa route với regex | `/v1/book/info` | `/v1/book123/info` |

### 3.1. `*` và `**` không giống nhau

`*` chỉ đại diện cho ký tự **bên trong một segment**. Ví dụ:

~~~text
Pattern:  /files/*
Match:    /files/a.txt
Not:      /files/2026/a.txt
~~~

`**` đại diện cho **nhiều segment** và có thể match cả phần path rỗng khi nó ở cuối. Ví dụ:

~~~text
Pattern: /files/**
Match:   /files
Match:   /files/a.txt
Match:   /files/archive/2026/a.txt
~~~

Với `PathPatternParser`, `**` **chỉ được đặt ở cuối** để không tạo ra những tình huống khó so sánh mức độ cụ thể. Ví dụ sau **không hợp lệ** với parser:

~~~text
/**/admin
/assets/**/download
/{*path}/thumbnail
~~~

Nếu có source cũ dùng `/**/admin`, không thể đơn giản giữ nguyên pattern đó khi chuyển sang `PathPatternParser`. Cần thiết kế lại route hoặc giữ `AntPathMatcher` nếu ràng buộc legacy thực sự yêu cầu cú pháp đó.

### 3.2. Biến `{id}` và biến có regex

~~~java
@GetMapping("/products/{id}")
public String byId(@PathVariable String id) {
    return "product:" + id;
}
~~~

`{id}` nhận **một segment**, ví dụ `/products/42` thì `id="42"`. Dấu gạch chéo phân chia segment nên `/products/42/spec` là URL khác.

Để hạn chế định dạng:

~~~java
@GetMapping("/products/{id:[0-9]+}")
public String numericId(@PathVariable String id) {
    return "numeric:" + id;
}
~~~

Biểu thức `[0-9]+` yêu cầu **ít nhất một chữ số**, ví dụ `/products/42` hợp lệ, `/products/abc` không khớp pattern này.

Lưu ý: regex nằm trong một **URI variable pattern**, không thay thế Bean Validation hoặc kiểm tra business rule. Một `Long` path variable vẫn cần chuyển kiểu, xử lý overflow, ID không tồn tại, phân quyền và truy cập dữ liệu.

Trong Java source, khi viết regex chứa dấu gạch chéo ngược như `\d+`, phải escape đúng Java string, ví dụ `"@GetMapping(...)"` với nội dung pattern `{id:\\d+}`; cách đơn giản trong ví dụ chính là dùng `[0-9]+` để tránh nhầm các lớp escaping.

### 3.3. `{*path}` bắt nhiều segment

`{*path}` là cú pháp **capture-the-rest**. Ví dụ:

~~~text
Pattern: /files/{*path}
Request: /files/reports/2026/summary.csv
Captured: path = "/reports/2026/summary.csv"
~~~

Khác với `{name}`, biến catch-all có thể chứa dấu `/`. Điều này hữu ích cho handler phục vụ đường dẫn logic, định tuyến tài nguyên hoặc kiểm tra phần route còn lại.

**Không dùng giá trị catch-all trực tiếp như đường dẫn file hệ điều hành.** Trước khi truy cập file/directory, phải áp dụng chính sách tên tài nguyên, kiểm soát path traversal, canonicalization, authorization và giới hạn đường dẫn. Việc parser match được route không có nghĩa input đã an toàn.

### 3.4. Literal, wildcard và dấu chấm

Pattern `/files/{name}` có thể nhận tên như `readme.txt`; dấu chấm không tự biến thành đuôi file dùng để chọn handler khác. Với Spring MVC hiện đại, cơ chế suffix pattern matching kiểu cũ không còn là điều nên dựa vào. Nếu API muốn `/files/{name}.json` thì hãy khai báo route và response type rõ ràng.

Ví dụ `/images/*.png` match một segment có hậu tố `.png`; không nên đồng nhất wildcard của URL với glob của shell hay biểu thức chính quy Java đầy đủ.

## 4. Pattern hợp lệ và pattern dễ gây lỗi khi migration

| Cách viết | `PathPatternParser` | Cách xử lý |
|---|---|---|
| `/api/{id}` | Hợp lệ | Capture một segment |
| `/api/{id:[0-9]+}` | Hợp lệ | Hạn chế định dạng ID bằng regex |
| `/docs/**` | Hợp lệ | Catch-all cuối |
| `/docs/{*path}` | Hợp lệ | Catch-all cuối, có biến |
| `/assets/**/thumb` | **Không hợp lệ** | Thiết kế lại URL hoặc cân nhắc matcher legacy |
| `/**/admin` | **Không hợp lệ** | Chuyển thành tiền tố rõ ràng hoặc route cụ thể |
| `/{*path}/details` | **Không hợp lệ** | Không đặt capture-the-rest trước đoạn khác |
| `/api/*/status` | Hợp lệ | Wildcard đúng một segment |
| `/api/v?/status` | Hợp lệ | Wildcard một ký tự |
| `/api/**/status/**` | **Không hợp lệ** | Không sử dụng `**` ở giữa |

Một route không hợp lệ có thể gây `PatternParseException` khi Spring parse đăng ký mapping trong quá trình khởi động, chứ không chỉ gây 404 khi client gọi. Vì vậy, trước khi bật parser trên ứng dụng legacy lớn, hãy rà tất cả `@RequestMapping`, `@GetMapping`, custom mapping, endpoint plugin và các pattern được cung cấp bởi thư viện.

## 5. Spring MVC chọn mapping nào khi nhiều pattern cùng match?

Một controller có thể có:

~~~java
@GetMapping("/catalog/featured")
public String featured() {
    return "featured";
}

@GetMapping("/catalog/{slug}")
public String bySlug(@PathVariable String slug) {
    return "slug:" + slug;
}

@GetMapping("/catalog/{*path}")
public String nested(@PathVariable String path) {
    return "nested:" + path;
}
~~~

Với request `GET /catalog/featured`, các pattern có thể cùng match, nhưng mapping literal `/catalog/featured` cụ thể hơn biến một segment và catch-all nên được chọn. Với `GET /catalog/books`, mapping `{slug}` có thể được chọn; với `GET /catalog/archive/2026`, mapping `{*path}` phục vụ phần path nhiều segment.

`PathPattern.SPECIFICITY_COMPARATOR` là cơ chế so sánh dành cho parsed patterns. Ý tưởng quan trọng:

1. **Catch-all** như `/**` và `/{*path}` được xếp sau mapping cụ thể không catch-all.
2. Trong các mapping không catch-all, path có cấu trúc cụ thể hơn (ít wildcard/biến hơn) được ưu tiên.
3. Khi mức độ phức tạp tương đương, độ dài chuẩn hóa và các điều kiện khác được sử dụng để phân biệt.
4. Các điều kiện HTTP method, params, headers, consumes, produces và cấu hình request mapping **cũng góp phần** vào việc một handler có được chọn không.

Đừng suy đoán rằng “method được khai báo trước thắng” hoặc “regex luôn ưu tiên hơn mọi route khác”. Để bảo đảm hành vi, hãy đặt URL không chồng lấp khi có thể và tạo regression tests cho những route có giao nhau.

### Mapping trùng và không thể phân biệt

Nếu hai method annotation có điều kiện mapping giống hệt, `RequestMappingHandlerMapping` có thể báo lỗi **ambiguous mapping** khi khởi động. Nếu nhiều mapping chỉ chồng lấp trên một số request, sự mơ hồ có thể lộ ra khi nhận chính request đó.

Sửa bằng cách phân biệt đường dẫn, method, media type hoặc các request conditions khác; **không** dựa vào thứ tự bean scan.

## 6. Trailing slash, chữ hoa/thường và ranh giới segment

### 6.1. Dấu `/` cuối đường dẫn

Trong Spring Framework 6.2, `PathPatternParser` mặc định **không tự coi** `/api/books` và `/api/books/` là cùng một route. Từ Spring Framework 6.0, cấu hình match optional trailing separator đã chuyển mặc định thành `false` và phương thức tương ứng được đánh dấu deprecated.

Ví dụ:

~~~text
@GetMapping("/api/books")

GET /api/books    => khớp
GET /api/books/   => không tự động khớp vì dấu "/" cuối
~~~

Trong app đơn giản, trường hợp không match thường dẫn đến HTTP 404. Nếu hệ thống muốn hỗ trợ cả hai dạng URL, có thể khai báo hai mapping rõ ràng, thực hiện redirect canonical URL ở edge/filter hoặc chọn một chuẩn URL và bắt client tuân theo. Không nên bật lại cơ chế trailing slash cũ một cách thiếu kiểm soát vì có thể phát sinh khác biệt bảo mật giữa các tầng.

### 6.2. Phân biệt chữ hoa/thường

`PathPatternParser` mặc định **case-sensitive**. `/api/books` và `/api/Books` là khác nhau. Nên quyết định cách đặt path API thống nhất, thường dùng chữ thường/kebab-case, thay vì trông đợi parser tự chuẩn hóa chữ.

Có thể cấu hình parser nâng cao `setCaseSensitive(false)`, nhưng thay đổi đó làm mở rộng tập URL khớp và cần kiểm thử security request matchers, cache key và URL canonicalization.

### 6.3. Encoding, semicolon và matrix variables

Một request path có thể chứa percent-encoded characters (ví dụ `%20` cho dấu cách) hoặc semicolon path parameters. Parsed path cho phép xử lý theo từng segment và hỗ trợ trích xuất matrix variables khi controller áp dụng.

Ví dụ cú pháp URL có matrix parameter:

~~~text
/cars/42;color=red;year=2026
~~~

Những phần sau dấu chấm phẩy không nên được xử lý bằng thao tác `String.split(";")` tùy ý trong code bảo mật. Hệ thống proxy/container/security firewall có thể giới hạn ký tự này; hãy chỉ sử dụng matrix variables khi contract API và hạ tầng hỗ trợ, đồng thời kiểm thử end-to-end.

**Encoded slash (`%2F`)** là ví dụ quan trọng: parsed matching xử lý các segment có nhận biết cấu trúc, nhưng Tomcat, proxy và firewall có thể chặn request chứa slash đã encode. Không bao giờ giả định URL chứa `%2F` sẽ đi đến controller hoặc tự động trở thành một segment hợp lệ ở mọi môi trường.

## 7. Cách cấu hình chiến lược trong Spring Boot 3.5

Spring Boot hỗ trợ property:

~~~properties
spring.mvc.pathmatch.matching-strategy=path-pattern-parser
~~~

Giá trị trên chọn **parser hiện đại** và là chiến lược mặc định cho MVC Boot 3.5 trong cấu hình thông thường; thường **không cần khai báo** nếu muốn giữ mặc định.

Nếu phải dùng tương thích với path pattern legacy:

~~~properties
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
~~~

Đây là một thay đổi có tác động đến **MVC handler mapping**: mã dùng riêng cú pháp `PathPatternParser` như `{*path}` cần rà soát và có thể phải viết lại khi dùng Ant matcher.

Cấu hình YAML tương đương:

~~~yaml
spring:
  mvc:
    pathmatch:
      matching-strategy: path-pattern-parser
~~~

Hoặc chọn legacy:

~~~yaml
spring:
  mvc:
    pathmatch:
      matching-strategy: ant-path-matcher
~~~

Không đặt cùng lúc hai giá trị mâu thuẫn trong nhiều nguồn config rồi giả định giá trị đầu tiên thắng. Spring Boot có thứ tự ưu tiên cho environment variables, profile, command-line args và file cấu hình; kiểm tra giá trị hiệu lực khi debug.

### 7.1. Vì sao không mặc định quay về AntPathMatcher?

`PathPatternParser` được Spring Framework khuyến nghị cho web routing vì cấu trúc path rõ ràng, xử lý encoding hợp lý hơn và khả năng match đã tối ưu. `AntPathMatcher` chủ yếu hữu ích trong yêu cầu tương thích cú pháp/Servlet mapping legacy. Chuyển về legacy vì muốn “sửa nhanh 404” mà không hiểu nguyên nhân có thể che giấu lỗi URL và tạo khác biệt với security matcher.

Quy trình khuyến nghị: **giữ parser mặc định**, sửa những mẫu không hợp lệ, kiểm thử trailing slash và encoding, chỉ đổi sang Ant nếu có ràng buộc kỹ thuật thực sự cần.

### 7.2. Phạm vi áp dụng

`spring.mvc.pathmatch.matching-strategy` cấu hình request mapping của **Spring MVC**. Nó không phải property để thay bộ định tuyến của Spring WebFlux, không thay servlet container Tomcat/Jetty, không tự thêm prefix vào route và không làm thay đổi HTTP method/path do client gửi.

Nếu project có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot mặc định thường chọn **Servlet MVC**; xác định loại web application thực tế trước khi cấu hình.

## 8. Trường hợp đặc biệt: `spring.mvc.servlet.path` và `server.servlet.context-path`

Hai property có ý nghĩa khác nhau:

- `server.servlet.context-path=/portal`: đặt **Servlet application context** dưới `/portal`.
- `spring.mvc.servlet.path=/api`: đặt **prefix mapping của DispatcherServlet** dưới `/api`.

Ví dụ controller `@GetMapping("/hello")` với cả hai sẽ được gọi bằng URL `/portal/api/hello` khi cấu hình tương thích.

**Điểm cần nhớ cho Spring Boot 3.5:** tài liệu Servlet Web Applications của Boot 3.5 ghi rõ chiến lược PathPattern mặc định **không tương thích với cấu hình prefix của DispatcherServlet thông qua `spring.mvc.servlet.path`**. Trong trường hợp đó, Boot hướng dẫn đổi:

~~~properties
server.port=8080
server.servlet.context-path=/portal
spring.mvc.servlet.path=/api
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
~~~

Điều này **không** có nghĩa chỉ dùng `server.servlet.context-path` là phải quay về Ant matcher. Khi DispatcherServlet vẫn map mặc định `/`, parser hiện đại vẫn là lựa chọn hợp lý.

Lưu ý: tài liệu cấp Spring Framework có mô tả khả năng hỗ trợ một số dạng servlet prefix mapping đơn giản, nhưng với ứng dụng Boot 3.5 hãy tuân thủ giới hạn và cách cấu hình được Boot phát hành cho phiên bản đó. Nếu muốn chuyển sang parser cùng custom Servlet mapping trong hệ thống nâng cao, cần kiểm chứng toàn bộ bằng version/framework setup thực tế, không coi mặc định được hỗ trợ.

**Quan trọng cho code migration:** sau khi bật `ant-path-matcher`, một `@GetMapping("/files/{*path}")` trong ví dụ parser ở dưới không còn là lựa chọn tương thích. Phải thiết kế lại route (ví dụ sử dụng `/files/**` và cách trích path được kiểm thử riêng), chứ không đơn thuần thay một dòng properties rồi tuyên bố toàn bộ API giữ nguyên.

## 9. Ví dụ Maven Spring MVC hoàn chỉnh theo PathPatternParser

Tạo project với cấu trúc:

~~~text
path-pattern-demo/
  pom.xml
  src/main/resources/application.properties
  src/main/java/com/example/pathdemo/
    PathPatternDemoApplication.java
    PathController.java
  src/test/java/com/example/pathdemo/
    PathRoutingIntegrationTest.java
~~~

### 9.1. POM dành cho Java 17+, Spring Boot 3.5

Tạo `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>path-pattern-demo</artifactId>
    <version>1.0.0</version>

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

`spring-boot-starter-web` mang Spring MVC và embedded servlet server mặc định. `spring-boot-starter-test` mang JUnit 5 và những công cụ test của Spring Boot. Dùng parent để quản lý phiên bản thư viện phù hợp thay vì tự chỉ định Spring Framework version khác với Boot.

### 9.2. Entry point Java

`src/main/java/com/example/pathdemo/PathPatternDemoApplication.java`:

~~~java
package com.example.pathdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PathPatternDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PathPatternDemoApplication.class, args);
    }
}
~~~

### 9.3. Các route literal, single-variable, regex và catch-all

`src/main/java/com/example/pathdemo/PathController.java`:

~~~java
package com.example.pathdemo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class PathController {

    @GetMapping(
        path = "/catalog/featured",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public String featured() {
        return "featured";
    }

    @GetMapping(
        path = "/catalog/{slug}",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public String catalogItem(@PathVariable String slug) {
        return "slug:" + slug;
    }

    @GetMapping(
        path = "/files/{name}",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public String file(@PathVariable String name) {
        return "file:" + name;
    }

    @GetMapping(
        path = "/files/{*path}",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public String nestedFile(@PathVariable String path) {
        return "nested:" + path;
    }

    @GetMapping(
        path = "/orders/{id:[0-9]+}",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public String numericOrder(@PathVariable String id) {
        return "order:" + id;
    }

    @GetMapping(
        path = "/docs",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public String docs() {
        return "docs";
    }

    @GetMapping(
        path = "/case",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public String caseSensitive() {
        return "lowercase";
    }
}
~~~

**Phân tích:**

- `/catalog/featured` là route literal; nó cụ thể hơn `/catalog/{slug}` khi `slug="featured"`.
- `/files/{name}` chỉ bắt một segment và phù hợp với `/files/readme.txt`.
- `/files/{*path}` bắt phần còn lại, ví dụ `/files/a/b` thì biến `path` là `"/a/b"`. Capture-the-rest có thể chứa dấu `/` mở đầu.
- `/orders/{id:[0-9]+}` chỉ match ID gồm chữ số theo regex.
- `/docs` và `/case` phục vụ hai ví dụ về dấu gạch chéo cuối và chữ hoa/thường.
- Mỗi method trả một `String` từ `@RestController` kèm `produces=text/plain` nên response body đơn giản, không phải tên view.
- Không định nghĩa hai method có cùng signature mapping nên không có xung đột registration trong ví dụ này.

### 9.4. Cấu hình ứng dụng

`src/main/resources/application.properties`:

~~~properties
server.port=8080

# Spring Boot 3.5: lựa chọn mặc định, khai báo rõ để học tập.
spring.mvc.pathmatch.matching-strategy=path-pattern-parser
~~~

Dự án **không** đặt `spring.mvc.servlet.path`, nên không gặp ràng buộc Servlet prefix của Boot 3.5. Không cần gắn thêm cấu hình đặc biệt để sử dụng `{*path}`.

## 10. Chạy chương trình và kiểm tra URL

Ở thư mục chứa `pom.xml`, với JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Hoặc đóng gói JAR:

~~~bash
mvn clean package
java -jar target/path-pattern-demo-1.0.0.jar
~~~

Với ứng dụng đang lắng nghe cổng 8080, thử lần lượt:

~~~bash
curl -i http://localhost:8080/api/catalog/featured
curl -i http://localhost:8080/api/catalog/books
curl -i http://localhost:8080/api/files/readme.txt
curl -i http://localhost:8080/api/files/a/b
curl -i http://localhost:8080/api/orders/123
curl -i http://localhost:8080/api/orders/abc
curl -i http://localhost:8080/api/docs
curl -i http://localhost:8080/api/docs/
curl -i http://localhost:8080/api/Case
~~~

Bảng phản hồi mong đợi với cấu hình và source code trên:

| URL | Trạng thái | Response body / lý do |
|---|---|---|
| `/api/catalog/featured` | 200 | `featured` |
| `/api/catalog/books` | 200 | `slug:books` |
| `/api/files/readme.txt` | 200 | `file:readme.txt` |
| `/api/files/a/b` | 200 | `nested:/a/b` |
| `/api/orders/123` | 200 | `order:123` |
| `/api/orders/abc` | 404 | Không match regex của order ID; không có route khác trong app mẫu |
| `/api/docs` | 200 | `docs` |
| `/api/docs/` | 404 | Trailing slash không tự được chấp nhận theo mặc định |
| `/api/Case` | 404 | Parser mặc định phân biệt chữ hoa/thường |

Các mã 404 trên giả định không thêm custom fallback, redirect, security hoặc static resource có thể phục vụ chính URL đó. `curl -i` in thêm status line và HTTP headers; cột body chỉ nêu nội dung do controller trả về.

Nếu cổng 8080 đã bận, có thể chạy:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--server.port=9090
~~~

Sau đó thay 8080 bằng 9090 trong lệnh curl. Đổi cổng không làm thay đổi nguyên tắc chọn path pattern.

## 11. Kiểm thử tích hợp với random port

Tạo `src/test/java/com/example/pathdemo/PathRoutingIntegrationTest.java`:

~~~java
package com.example.pathdemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PathRoutingIntegrationTest {

    @LocalServerPort
    private int port;

    private final HttpClient client = HttpClient.newHttpClient();

    private HttpResponse<String> get(String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path))
                .GET()
                .build();
        return client.send(
                request,
                HttpResponse.BodyHandlers.ofString()
        );
    }

    @Test
    void literalIsMoreSpecificThanVariable() throws Exception {
        assertTrue(port > 0);
        HttpResponse<String> response =
                get("/api/catalog/featured");

        assertEquals(200, response.statusCode());
        assertEquals("featured", response.body());
    }

    @Test
    void oneSegmentVariableMatches() throws Exception {
        HttpResponse<String> response =
                get("/api/files/readme.txt");

        assertEquals(200, response.statusCode());
        assertEquals("file:readme.txt", response.body());
    }

    @Test
    void catchAllCapturesMultipleSegments() throws Exception {
        HttpResponse<String> response =
                get("/api/files/a/b");

        assertEquals(200, response.statusCode());
        assertEquals("nested:/a/b", response.body());
    }

    @Test
    void regexVariableAcceptsDigits() throws Exception {
        HttpResponse<String> response =
                get("/api/orders/123");

        assertEquals(200, response.statusCode());
        assertEquals("order:123", response.body());
    }

    @Test
    void regexVariableRejectsNonDigits() throws Exception {
        assertEquals(404, get("/api/orders/abc").statusCode());
    }

    @Test
    void trailingSlashDoesNotMatchByDefault() throws Exception {
        assertEquals(200, get("/api/docs").statusCode());
        assertEquals(404, get("/api/docs/").statusCode());
    }

    @Test
    void pathsAreCaseSensitiveByDefault() throws Exception {
        assertEquals(404, get("/api/Case").statusCode());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

`@SpringBootTest(RANDOM_PORT)` tạo embedded HTTP server thực, `@LocalServerPort` nhận cổng được bind. Đây là test thích hợp để quan sát path matching qua HTTP chứ không chỉ test method Java riêng lẻ. Bộ test bao quát độ cụ thể, biến một segment, catch-all, regex, trailing slash và case sensitivity.

Nếu chạy `@WebMvcTest` với MockMvc, bạn có thể test logic mapping ở cấp MVC; nhưng integration test dùng socket thật giúp phát hiện ảnh hưởng của Servlet context mapping, filter, container và proxy nội bộ rõ hơn.

## 12. Khi phải dùng AntPathMatcher cho mã cũ

`AntPathMatcher` là chiến lược dựa trên String path, được dùng nhiều ở các dự án Spring đời trước. Các trường hợp cân nhắc giữ Ant:

- Hệ thống có route legacy sử dụng `**` ở giữa pattern, ví dụ `/files/**/download`.
- Ứng dụng Spring Boot 3.5.x cần `spring.mvc.servlet.path=/api` và muốn tuân theo cấu hình tương thích được Boot hướng dẫn.
- Một số custom MVC mapping hoặc thư viện cũ dựa vào String path matching chưa được migration.
- Chi phí thay đổi API routing hiện tại lớn hơn lợi ích khi chuyển đổi; dự án có kế hoạch migration và regression tests rõ ràng.

**Cách bật:**

~~~properties
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
~~~

Ví dụ riêng cho kiểu legacy:

~~~java
@RestController
class LegacyController {

    @GetMapping("/legacy/**/download")
    public String download() {
        return "legacy download";
    }
}
~~~

Đây là **class minh họa dùng với chiến lược Ant matcher**, không được đưa vào project mặc định parser ở mục 9 vì `**` xuất hiện giữa pattern. Với Ant matcher, `GET /legacy/a/b/download` có thể match route này. Các pattern khác, đặc biệt `{*path}` của parser, phải được rà và chuyển đổi khi đổi chiến lược.

Không có khuyến nghị “chuyển lại Ant luôn tốt hơn”. Lựa chọn có tradeoff:

| Tiêu chí | `PathPatternParser` | `AntPathMatcher` |
|---|---|---|
| Biểu diễn pattern | `PathPattern` đã parse | `String` pattern |
| Biểu diễn đường dẫn | `RequestPath`/`PathContainer` theo segment | String lookup path |
| `**` ở giữa | Không hỗ trợ | Có thể hỗ trợ |
| `{*path}` capture phần còn lại | Có | Không phải cú pháp tương thích trực tiếp |
| Encoded path và semicolon | Thiết kế xử lý theo segment | Cần giải quyết string decode/lookup path cẩn thận |
| Hiệu năng matching | Hướng đến match hiệu quả và ít ambiguity | Có nhiều chi phí xử lý String và lựa chọn pattern hơn |
| Mặc định Spring MVC 6.2/Boot 3.5 | Có | Không |
| Khi dùng `spring.mvc.servlet.path` của Boot 3.5 | Có caveat tương thích từ Boot | Boot hướng dẫn dùng chiến lược này |
| Spring WebFlux | Sử dụng parsed pattern | Không phải tùy chọn dùng để thay thế WebFlux parser |

Nếu chuyển chiến lược, cần kiểm tra toàn bộ route thay vì chỉ thực hiện smoke test một endpoint. Riêng regex URI variable, wildcard, catch-all, suffix, trailing slash và encoding có thể tạo khác biệt.

## 13. Tùy chỉnh parser nâng cao bằng WebMvcConfigurer

Khi cần thay một lựa chọn của parser, Spring MVC có API `PathMatchConfigurer`. Ví dụ **fragment cấu hình nâng cao**, không nằm trong project mẫu ở mục 9:

~~~java
package com.example.pathdemo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.PathMatchConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.util.pattern.PathPatternParser;

@Configuration
public class CustomPathMatching implements WebMvcConfigurer {

    @Override
    public void configurePathMatch(PathMatchConfigurer configurer) {
        PathPatternParser parser = new PathPatternParser();
        parser.setCaseSensitive(false);

        configurer.setPatternParser(parser);
    }
}
~~~

Khi đăng ký bean trên trong app, một số controller routes vốn chỉ nhận URL chữ thường có thể match thêm URL chữ hoa; **các test case-sensitive ở mục 11 sẽ không còn đúng**. Đây là minh họa về tác động của cấu hình, không phải khuyến nghị mặc định.

Không dùng `@EnableWebMvc` chỉ nhằm chỉnh một tùy chọn path matching: trong Spring Boot, thêm `@EnableWebMvc` có thể thay thế/loại một phần MVC auto-configuration và kéo theo nhiều hệ quả như static resource handling, converter và CORS. Dùng `WebMvcConfigurer` là cách tích hợp nhẹ hơn khi có yêu cầu cấu hình MVC mở rộng.

Nếu cần prefix cho **annotated controllers** mà không phải servlet prefix, Spring MVC cũng hỗ trợ:

~~~java
@Override
public void configurePathMatch(PathMatchConfigurer configurer) {
    configurer.addPathPrefix(
            "/api",
            org.springframework.web.method.HandlerTypePredicate
                    .forAnnotation(RestController.class)
    );
}
~~~

Đây là **method fragment** trong một `WebMvcConfigurer`, không phải file Java độc lập. Nó thêm prefix vào **mẫu của controller được chọn**, khác về tầng cấu hình so với `spring.mvc.servlet.path`. Khi chọn cách này, tránh trùng prefix đã khai báo trong `@RequestMapping`, và kiểm tra Security/Actuator paths phù hợp.

Không đăng ký đồng thời hai triển khai `configurePathMatch` trên cùng class chỉ để ghép các đoạn ví dụ; khi cần nhiều tùy chỉnh hãy viết chung vào một method và kiểm thử.

## 14. Phân biệt MVC PathPatternParser với WebFlux routing

Spring WebFlux dùng `DispatcherHandler` và cơ chế mapping reactive khác Spring MVC `DispatcherServlet`. Dù WebFlux cũng sử dụng parsed `PathPattern`, cấu hình:

~~~properties
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
~~~

**không chuyển WebFlux sang Ant matcher**. Với WebFlux, parsed patterns là mô hình route chính thức và không có một lựa chọn tương đương để dùng Ant matcher cho toàn bộ reactive handler mappings.

Nếu project có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Boot thường chọn **Servlet MVC** khi tự phát hiện web application type. Đừng chỉ nhìn dependency WebFlux trên classpath mà kết luận toàn bộ API đang chạy reactive.

Cũng cần phân biệt **WebMvc.fn RouterFunction** với annotated controller. Cả hai dùng Spring MVC nhưng cơ chế chọn functional handler có router predicates riêng; không mặc định mọi hành vi ưu tiên route của WebMvc.fn giống hệt `RequestMappingHandlerMapping`.

## 15. Các lỗi thường gặp và cách xử lý

### 15.1. `PatternParseException` khi khởi động

**Nguyên nhân:** route dùng cú pháp bị parser cấm, chẳng hạn:

~~~java
@GetMapping("/legacy/**/download")
~~~

**Khắc phục:** sửa thành các route cụ thể hơn, hoặc thiết kế catch-all cuối route khi phù hợp; chỉ chọn `ant-path-matcher` nếu thực sự cần tương thích legacy và đã kiểm thử những endpoint sử dụng pattern riêng của parser.

### 15.2. URL trước đây hoạt động, nay trả 404 vì dấu gạch chéo cuối

**Nguyên nhân:** `/api/orders` không tự đồng nghĩa `/api/orders/` trong Framework 6.2. Giải quyết bằng quy tắc canonical URL, khai báo mapping rõ ràng hoặc redirect phù hợp. Tránh giả định một property cũ sẽ tự bật lại behavior đã deprecated.

### 15.3. Route có `{*path}` nhưng không match sau khi chuyển sang Ant

`{*path}` là cú pháp dành cho parsed `PathPattern`. Nếu cấu hình chuyển `ant-path-matcher` để hỗ trợ `spring.mvc.servlet.path`, hãy đổi route catch-all sang pattern Ant phù hợp (ví dụ `/**` ở cuối), đồng thời thiết kế lại cách lấy phần đường dẫn còn lại. Không giữ nguyên `@PathVariable("path")` và kỳ vọng nó được bind theo cơ chế parser.

### 15.4. `@GetMapping("/{id}")` bắt nhầm một path literal

Khi có `/catalog/featured` và `/catalog/{slug}`, Spring MVC chọn route cụ thể hơn, không phụ thuộc thứ tự khai báo trong Java. Nếu request vào handler khác dự kiến, kiểm tra path conditions, `consumes`/`produces`, class-level mapping, context path và mapping đăng ký thật.

### 15.5. Regex URI variable không match

`/orders/{id:[0-9]+}` chấp nhận chuỗi số, không nhận chữ cái. Nếu muốn ID dạng UUID hoặc slug, định nghĩa pattern phù hợp; đừng nới lỏng regex một cách ngẫu nhiên để “chữa 404”. Kiểm tra cú pháp escape Java nếu dùng `\d`, `\w` và các ký tự đặc biệt.

### 15.6. Encoded slash, semicolon hoặc Unicode hoạt động khác giữa các môi trường

Chúng có thể bị reverse proxy, embedded server, WAF hoặc Spring Security firewall xử lý trước khi vào controller. Để chẩn đoán, kiểm tra request URI thực tế tại từng hop, chính sách decode/normalize và pattern được đăng ký. Đừng chỉ thay matcher để cố vượt qua chính sách bảo vệ URL.

### 15.7. `spring.mvc.servlet.path` làm parser mặc định không tương thích

Với Boot 3.5, nếu phải đặt DispatcherServlet prefix qua `spring.mvc.servlet.path`, làm theo tài liệu Boot: `spring.mvc.pathmatch.matching-strategy=ant-path-matcher`. Nếu không có nhu cầu map DispatcherServlet riêng, có thể chỉ dùng `server.servlet.context-path` mà giữ parser mặc định.

### 15.8. Dùng `@EnableWebMvc` và thấy nhiều tính năng Boot mất tác dụng

`@EnableWebMvc` có thể giành quyền cấu hình MVC thay Boot auto-config. Gỡ nếu không thực sự cần điều khiển toàn bộ MVC. Thay bằng `WebMvcConfigurer` cho những tùy chỉnh bổ sung, đồng thời kiểm tra lại routing, formatters, CORS và static resources.

### 15.9. Mã chạy nhưng security matcher bảo vệ URL sai

Nếu Security sử dụng path matcher với logic khác MVC, những URL lạ có thể match controller nhưng không match rule bảo vệ (hoặc ngược lại). Thiết kế security theo resource/HTTP method rõ ràng, ưu tiên matcher phù hợp stack, áp dụng deny-by-default và test 401/403 cho các URL đặc biệt, dấu `/` cuối, encoded delimiters và route catch-all.

### 15.10. 404 khó phân biệt với lỗi phục vụ file tĩnh

Spring Boot thường có static resource handler phục vụ `/**`. Một request không match controller có thể được đưa tới resource handler rồi mới trả lỗi do thiếu file. Do đó, log hoặc exception có thể là `NoResourceFoundException` thay vì `NoHandlerFoundException`. Phân biệt controller mapping và resource handler khi đọc lỗi. Không xóa mapping static resources chỉ để đổi exception class nếu ứng dụng vẫn cần phục vụ tài nguyên.

## 16. Checklist migration và kiểm thử trước khi triển khai

1. **Xác định web stack và version**: Spring MVC Boot 3.5/Framework 6.2 hay WebFlux; không suy ra từ một dependency duy nhất.
2. **Liệt kê route** từ annotation và custom mapping; tìm `**` ở giữa, `{*path}`, route trùng, regex phức tạp và các fallback.
3. **Giữ PathPatternParser mặc định** nếu không có ràng buộc tương thích cụ thể. Chỉ chuyển về Ant khi biết rõ lý do.
4. **Kiểm tra Servlet prefix**: `server.servlet.context-path` khác với `spring.mvc.servlet.path`; với Boot 3.5, dùng Ant matcher khi cấu hình DispatcherServlet prefix theo hướng dẫn của Boot.
5. **Kiểm thử match specificity**: literal so với variable, một segment so với catch-all, hai mapping giao nhau, mapping ambiguity.
6. **Kiểm thử định dạng URL**: chữ hoa/thường, trailing slash, đuôi file, encoded characters, semicolon, ký tự Unicode và query string.
7. **Kiểm thử HTTP method/media type**: GET/POST, `Accept`, `Content-Type`, 404/405/406/415.
8. **Đối chiếu security filter/rule** với controller matching, đặc biệt catch-all và rewrite ở proxy.
9. **Dùng integration test HTTP thật** trên `RANDOM_PORT`; kiểm tra thêm qua ingress/gateway khi production có proxy.
10. **Quan sát route thực tế** bằng endpoint Actuator mappings trong môi trường bảo vệ phù hợp, log MVC có kiểm soát hoặc unit test chuyên biệt.
11. **Không phát hành chỉ dựa vào startup thành công**: cần chạy regression tests, đo ảnh hưởng lên API/clients và chuẩn bị rollback.
12. **Không dựa vào thuật toán match cho phân quyền**: authorization phải được kiểm tra độc lập sau khi path handler đã được xác định đúng.

## Tài liệu chính thức

- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): parser mặc định, property chọn strategy và giới hạn với `spring.mvc.servlet.path`.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): tham số `spring.mvc.pathmatch.matching-strategy`.
- [Spring Framework 6.2 — Mapping Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-requestmapping.html): URI patterns, request mapping conditions và chọn pattern phù hợp.
- [Spring Framework 6.2 — Path Matching](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/handlermapping-path.html): decoded path segments và so sánh mô hình parsed/string.
- [Spring Framework 6.2 — MVC Path Matching Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/path-matching.html): `WebMvcConfigurer` và `PathMatchConfigurer`.
- [Spring Framework 6.2 — PathPattern Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/web/util/pattern/PathPattern.html): định nghĩa `*`, `?`, `**`, `{var}`, `{*var}`.
- [Spring Framework 6.2 — PathPatternParser Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/web/util/pattern/PathPatternParser.html): lựa chọn parser, case sensitivity và trailing slash behavior.

**Kết luận:** `PathPatternParser` là lựa chọn mặc định và nên ưu tiên cho Spring MVC hiện đại. Sử dụng đúng cú pháp segment, đặt `**`/`{*path}` ở cuối, kiểm tra độ cụ thể và các URL đặc biệt. Chỉ chọn `AntPathMatcher` khi có nhu cầu tương thích thực tế, đặc biệt ở cấu hình `spring.mvc.servlet.path` của Spring Boot 3.5, và luôn hồi quy toàn bộ handler mappings trước khi triển khai.
