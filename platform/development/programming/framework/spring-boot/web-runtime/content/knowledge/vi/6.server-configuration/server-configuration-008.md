# Mã hóa ký tự, URI và xử lý Unicode trong Spring Boot Web Runtime

## 1. Mục tiêu học tập

Trong một ứng dụng Spring Boot phục vụ HTTP, dữ liệu tiếng Việt có dấu, tên người dùng tiếng Nhật, chữ Ả Rập hoặc emoji có thể đi qua nhiều bước khác nhau: từ trình duyệt, URL, reverse proxy, HTTP connector, Servlet API, Spring MVC, JSON converter cho đến cơ sở dữ liệu. Nếu một bước dùng sai cách giải mã, người dùng sẽ thấy ký tự hỏng, URL sai, HTTP 400/404 hoặc dữ liệu trông giống nhau nhưng so sánh không bằng nhau.

Bài này thuộc nhóm **Cấu hình máy chủ** và tập trung vào:

1. Phân biệt **Unicode**, **UTF-8**, **UTF-16**, **percent-encoding trong URI** và **HTML form encoding**.
2. Hiểu ba đường dữ liệu độc lập: **URI path/query**, **HTTP request body** và **HTTP response body**.
3. Cấu hình **server.servlet.encoding.\*** và **server.tomcat.uri-encoding** cho Spring Boot chạy trên Servlet/Tomcat.
4. Nhận, xử lý và trả về Unicode trong Spring MVC mà không tự mã hóa hoặc giải mã hai lần.
5. Kiểm thử end-to-end và khắc phục lỗi ký tự tiếng Việt, emoji, ký tự đặc biệt, path bị từ chối và Unicode normalization.
6. Nhận biết giới hạn của cấu hình Servlet khi ứng dụng dùng **Spring WebFlux / Reactor Netty**.

Ví dụ cấu hình và ứng dụng sử dụng **Spring Boot 3.5.x, Java 17+, Spring MVC và embedded Tomcat**. Với phiên bản Boot khác, hãy đối chiếu tài liệu của đúng dòng phiên bản vì tên property và cơ chế server có thể thay đổi.

## 2. Unicode không đồng nghĩa với UTF-8

**Unicode** định nghĩa các ký tự và mã điểm (code point). **Encoding** quy định cách biểu diễn những mã điểm đó thành các byte hoặc đơn vị mã.

- **UTF-8** là cách biểu diễn Unicode thành chuỗi byte, phổ biến trên HTTP, JSON, file cấu hình và hạ tầng web; mỗi Unicode scalar value sử dụng từ một đến bốn byte.
- **UTF-16** biểu diễn bằng các đơn vị 16 bit. Java String dùng các đơn vị mã UTF-16; ký tự ngoài Basic Multilingual Plane, ví dụ nhiều emoji, cần **surrogate pair** gồm hai đơn vị mã.
- **Charset** là tên encoding được dùng khi đổi byte thành String và ngược lại, ví dụ **UTF-8** hoặc **ISO-8859-1**.
- **Percent-encoding** trong URI là phép biểu diễn byte thành chuỗi **%HH** để dữ liệu an toàn trong URL. Nó không phải một charset độc lập: phải chọn charset (thường là UTF-8) **trước** khi đổi byte thành %HH.

Ví dụ chữ **é** có Unicode code point U+00E9; byte UTF-8 tương ứng là **C3 A9**, và khi đưa vào một URI component cần percent-encode thì thành **%C3%A9**.

Chuỗi tiếng Việt **Việt** có thể được dùng trong JSON hoặc Java String dưới dạng ký tự nguyên bản. Trong một URL, trình duyệt hoặc HTTP client thường biểu diễn phần non-ASCII bằng các chuỗi %HH sau khi mã hóa UTF-8.

**Mojibake** xảy ra khi cùng một byte được giải mã bằng charset sai. Ví dụ một chuỗi được ghi bằng UTF-8 nhưng đọc dưới charset khác có thể xuất hiện dạng **Tiáº¿ng Viá»‡t** thay vì **Tiếng Việt**. Việc đổi font không sửa được nguyên nhân này.

## 3. Phân biệt từng lớp khi một request đi vào máy chủ

~~~text
Người dùng gõ "Tiếng Việt 😀"
          |
          +-- URL path / query --> URI percent-encoding --> reverse proxy
          |                                             --> Tomcat URI decoding
          |                                             --> @PathVariable / @RequestParam
          |
          +-- Request body --> Content-Type + bytes --> HTTP message converter
                                                    --> @RequestBody / form parameter
          |
          +-- Controller và Service (Java String / Unicode)
                                                    --> DB, logs, file, APIs
          |
          +-- Response --> HTTP message converter --> UTF-8 bytes --> Client
~~~

Có **ba quyết định encoding riêng**:

| Kênh dữ liệu | Cơ chế giải mã | Ví dụ | Cấu hình cần quan tâm |
|---|---|---|---|
| **Path của URI** | Server phân tích URL và percent-decode theo chính sách connector | **/users/Nguy%E1%BB%85n** | **server.tomcat.uri-encoding**, reverse proxy, quy tắc path |
| **Query parameter** | URL decoding và parameter parsing | **?name=C%C3%A0+ph%C3%AA** | URI encoding, quy tắc query/form |
| **Body JSON** | **HttpMessageConverter** và JSON parser | **{"name":"Hà Nội"}** | Content-Type, UTF-8 theo chuẩn JSON |
| **Body form** | Servlet parameter parsing | **application/x-www-form-urlencoded** | Request character encoding và Content-Type |
| **Body text/plain** | Text converter theo charset | Văn bản UTF-8 | **Content-Type: text/plain;charset=UTF-8** |
| **Response** | Converter hoặc response writer | JSON, HTML, text, file | Response Content-Type/charset và converter |

**Điểm cốt lõi:** cấu hình charset của **request body** không đồng nghĩa với việc cấu hình **URI decoding**. Một endpoint có thể nhận body Unicode đúng nhưng đọc sai path hoặc query nếu máy chủ, proxy hoặc client bất đồng về quy tắc mã hóa URL.

## 4. Cấu hình UTF-8 cho Spring Boot Servlet/Tomcat

Spring Boot 3.5 công bố các property liên quan trong **Common Application Properties** và mục **Character Encoding** của phần Servlet web applications.

Tạo hoặc cập nhật **src/main/resources/application.yml**:

~~~yaml
server:
  servlet:
    encoding:
      enabled: true
      charset: UTF-8
      force-request: true
      force-response: false
  tomcat:
    uri-encoding: UTF-8
~~~

Giải thích chính xác:

- **server.servlet.encoding.enabled=true**: bật hỗ trợ cấu hình character encoding ở tầng Servlet.
- **server.servlet.encoding.charset=UTF-8**: charset được cấu hình cho HTTP request/response; giá trị mặc định của Boot 3.5 là UTF-8.
- **server.servlet.encoding.force-request=true**: ép request dùng charset cấu hình trong phạm vi cơ chế encoding Servlet. Nếu không khai báo **force**, tùy chọn này mặc định là true ở Boot 3.5.
- **server.servlet.encoding.force-response=false**: không ép mọi response dùng cùng charset. Đây là lựa chọn phù hợp khi ứng dụng trả nhiều media type khác nhau và để converter thiết lập charset thích hợp. Giá trị mặc định phụ thuộc cơ chế force, cần xem tài liệu phiên bản.
- **server.tomcat.uri-encoding=UTF-8**: đặt encoding mà **Tomcat** dùng để giải mã các byte URI sau percent-decoding; mặc định trên Boot 3.5 là UTF-8.

Nếu toàn bộ ứng dụng cần ép charset cho cả request lẫn response ở tầng Servlet, có thể dùng:

~~~yaml
server:
  servlet:
    encoding:
      charset: UTF-8
      force: true
~~~

Hãy đánh giá ảnh hưởng của **force: true** với response text hoặc định dạng đặc thù trước khi bật. Property này không tự sửa các byte đã bị giải mã sai tại proxy, database hoặc HTTP client; cũng không chuyển dữ liệu nhị phân thành UTF-8.

### 4.1. Chức năng của CharacterEncodingFilter

Trong Servlet stack, Spring Boot thường đăng ký cơ chế **CharacterEncodingFilter** để áp dụng cấu hình request/response encoding. Việc thiết lập request charset phải xảy ra **trước khi** Servlet hoặc Filter khác đọc request body hoặc tham số form. Nếu một Filter tùy biến truy cập parameter quá sớm, rồi Filter encoding mới được chạy, charset có thể đã bị cố định và dữ liệu không thể phục hồi chỉ bằng đổi property.

Không nên tự tạo thêm nhiều filter encoding với thứ tự khác nhau nếu Boot đã cấu hình sẵn; ưu tiên khai báo property và kiểm tra filter chain thực tế.

### 4.2. Các property không thể hoán đổi

**server.tomcat.uri-encoding** chỉ tác động khi server đang chạy là **Tomcat**. Nếu đổi sang Jetty hoặc Undertow trên phiên bản Boot có hỗ trợ, phải kiểm tra cấu hình connector tương ứng; property Tomcat không điều khiển server khác.

**server.servlet.encoding.\*** dành cho **Servlet stack**. Với Spring WebFlux chạy trên **Reactor Netty**, cơ chế nhận/ghi body nằm ở HTTP codecs và reactive server, không dùng Servlet CharacterEncodingFilter. Trong WebFlux hãy dùng đúng Content-Type, cách tạo URI và cấu hình reactive server thích hợp.

**server.servlet.encoding.mapping.\*** có thể ánh xạ **locale → charset** cho response trong ứng dụng Servlet. Đây là cấu hình chuyên biệt, chẳng hạn mapping theo Accept-Language cho JSP/Servlet response; nó không có chức năng dịch ngôn ngữ và thường không cần trong API JSON UTF-8. Không cấu hình mapping locale nếu không có yêu cầu thực tế.

## 5. URI, URL và percent-encoding

Một URI thường có cấu trúc:

~~~text
https://example.com/search/C%C3%A0-ph%C3%AA?q=Vi%E1%BB%87t+Nam&sort=name#section
|----- origin -----|---- path ----------------|---- query --------------------| fragment
~~~

Các phần có quy tắc riêng:

- **Path** phân tách segment bởi dấu **/**. Dấu **/** có ý nghĩa cấu trúc, nên không được tự thay mọi ký tự bằng cùng một thuật toán form encoding.
- **Query** chứa các cặp tên/giá trị. Các ký tự **&** và **=** có ý nghĩa khi phân tích thành parameter; phải mã hóa nếu là dữ liệu thực.
- **Fragment** bắt đầu bằng **#** và thông thường chỉ được trình duyệt dùng phía client; nó **không được gửi** trong HTTP request-target tới server.
- Dấu **%** mở đầu một chuỗi percent-encoding. Dữ liệu có dấu phần trăm thật cần được mã hóa thích hợp thành **%25** khi xây dựng URL.

### 5.1. Mã hóa thành phần đúng cách

| Chuỗi đầu vào | Cách biểu diễn URL thông dụng | Lưu ý |
|---|---|---|
| **é** | **%C3%A9** | UTF-8 gồm C3 A9 |
| **Việt** | **Vi%E1%BB%87t** | Non-ASCII được percent-encode |
| **Cà phê** | **C%C3%A0%20ph%C3%AA** trong path | Dấu cách thành %20 |
| **Cà phê** | **C%C3%A0+ph%C3%AA** trong form/query theo form-style | Dấu cộng đại diện cho dấu cách |
| **A+B** | **A%2BB** khi là giá trị form | Plus thật phải được encode |
| **a&b** | **a%26b** khi là một query/form value | Tránh bị tách thành hai parameter |
| **a/b** | Cần xử lý như dữ liệu segment, không coi như path separator | %2F có thể bị proxy/server từ chối |

Không tự nối trực tiếp chuỗi người dùng vào URL nếu chuỗi có dấu **?**, **&**, **=**, **#**, **%**, dấu cách hoặc dấu tiếng Việt. Hãy dùng **URI builder** biết rõ thành phần là path hay query.

### 5.2. java.net.URLEncoder phù hợp với form, không phải toàn bộ URI

**URLEncoder** của Java triển khai quy tắc **application/x-www-form-urlencoded**: dấu cách trở thành dấu cộng (**+**). Nó rất phù hợp khi cần mã hóa form field, nhưng có thể gây nhầm lẫn khi dùng để tạo nguyên một path segment hoặc URL đầy đủ.

Ví dụ chạy độc lập với Java 17:

**UnicodeCheck.java**

~~~java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;

public class UnicodeCheck {
    public static void main(String[] args) {
        String value = "Cà phê & trà";
        System.out.println(URLEncoder.encode(value, StandardCharsets.UTF_8));

        String composed = "\u00E9";     // é dạng NFC
        String decomposed = "e\u0301";  // e + combining acute accent
        System.out.println(composed.equals(decomposed));
        System.out.println(composed.equals(
                Normalizer.normalize(decomposed, Normalizer.Form.NFC)));

        String emoji = "😀";
        System.out.println(emoji.length());
        System.out.println(emoji.codePointCount(0, emoji.length()));
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 UnicodeCheck.java
java UnicodeCheck
~~~

Stdout chính xác:

~~~text
C%C3%A0+ph%C3%AA+%26+tr%C3%A0
false
true
2
1
~~~

Dòng đầu là **form-style encoding**; dấu cộng thay dấu cách. Hai giá trị Unicode **é** và **e + dấu sắc kết hợp** nhìn gần như giống nhau nhưng không bằng nhau trước khi normalize. Emoji nằm ngoài BMP nên Java String có hai UTF-16 code units dù chỉ là một code point.

### 5.3. Dùng UriComponentsBuilder khi tạo URI trong Spring

Ví dụ dưới đây là **đoạn mã minh họa** cần chạy trong dự án đã có **spring-web**, khác với chương trình Java thuần ở trên:

~~~java
import org.springframework.web.util.UriComponentsBuilder;

String uri = UriComponentsBuilder
        .fromPath("/api/items/{name}")
        .encode()
        .buildAndExpand("Cà phê & trà")
        .toUriString();

System.out.println(uri);
~~~

Kết quả:

~~~text
/api/items/C%C3%A0%20ph%C3%AA%20%26%20tr%C3%A0
~~~

**UriComponentsBuilder#encode()** trước khi expand biến giúp mã hóa giá trị biến như dữ liệu, kể cả các ký tự reserved có thể mang nghĩa cấu trúc. Không percent-encode giá trị trước rồi truyền tiếp vào builder ở chế độ encode nếu không muốn **double encoding**, chẳng hạn **%C3%A0** biến thành **%25C3%25A0**.

Nếu giá trị do người dùng nhập vốn là một path chứa nhiều segment, phải quyết định rõ đây là **một segment dữ liệu** hay **các segment cấu trúc**; hai cách không tương đương.

### 5.4. Chú ý dấu cộng, dấu gạch chéo và quy tắc server

- Trong **application/x-www-form-urlencoded**, **+** đại diện cho dấu cách. Muốn gửi dấu cộng thật dùng **%2B**.
- Trong path, dấu **+** thường là ký tự dữ liệu hợp lệ, không được tự động xử lý giống form query.
- Dấu **%2F** là slash được percent-encode. Reverse proxy và Tomcat có thể từ chối hoặc có chính sách riêng đối với dấu slash mã hóa để ngăn path traversal và routing ambiguities.
- **Không** bật các tùy chọn nới lỏng URI của server chỉ để làm một URL sai hoạt động. Nếu identifier có slash hoặc ký tự đặc biệt, nên đặt nó trong query/body hoặc mã hóa theo cách thiết kế API an toàn.
- Không decode URL tùy tiện hai lần. **%252F** sau một lần decode có thể thành **%2F**, sau hai lần thành **/**, dẫn đến sai route và lỗ hổng bảo mật.
- Proxy, WAF, ingress và backend phải cùng hiểu quy tắc decode/normalize. Không được chỉ kiểm tra trên Tomcat rồi bỏ qua reverse proxy.

## 6. Body JSON, form và plain text

### 6.1. JSON theo UTF-8

Theo **RFC 8259**, JSON trao đổi giữa các hệ thống không thuộc môi trường đóng phải dùng **UTF-8**. Media type chuẩn là **application/json**; tài liệu đăng ký media type không định nghĩa tham số charset bắt buộc. Vì vậy header sau đã đủ cho JSON hiện đại:

~~~http
Content-Type: application/json
~~~

Ví dụ body JSON hợp lệ:

~~~json
{
  "name": "Nguyễn Hà",
  "city": "Hà Nội",
  "emoji": "😀"
}
~~~

Khi một Spring MVC controller nhận **@RequestBody** một record hoặc DTO từ JSON, Jackson và message converter tạo Java String từ body. Khi trả record, converter chuyển thành JSON theo encoding tương thích.

**Lưu ý:** JSON có thể biểu diễn một ký tự trực tiếp hoặc qua escape Unicode như **\u00E9**. Hai cách có thể cho cùng **giá trị String** sau khi parse dù chuỗi byte HTTP khác nhau. Không so sánh hai JSON response theo raw byte để kết luận sai Unicode khi khác biệt chỉ là escape.

Không thêm UTF-8 BOM vào JSON gửi qua mạng. Nếu body chứa byte được mã hóa theo một charset khác nhưng lại khai báo hoặc giả định UTF-8, server có thể báo lỗi parse hoặc nhận ký tự hỏng.

### 6.2. HTML form

Với **application/x-www-form-urlencoded**, client mã hóa **field name / field value** rồi gửi dưới dạng form-style string; dấu cách thường thành **+**. Java Servlet parameter parsing chịu ảnh hưởng từ request character encoding và cách giải mã của container.

Ví dụ body form sau biểu diễn giá trị **Cà phê & trà**:

~~~text
name=C%C3%A0+ph%C3%AA+%26+tr%C3%A0
~~~

Header thích hợp:

~~~http
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
~~~

Đặt **force-request: true** giúp áp dụng UTF-8 đồng nhất ở tầng Servlet, nhưng không thể sửa một client vốn gửi byte sai chuẩn. Nên kiểm tra thực tế với nhiều trình duyệt hoặc client tích hợp.

### 6.3. Plain text

Khi gửi một body text thuần, hãy khai báo charset rõ ràng, ví dụ:

~~~http
Content-Type: text/plain; charset=UTF-8
~~~

Khi trả plain text bằng **ResponseEntity<String>**, có thể đặt Content-Type gồm charset; khi trả JSON hãy dùng JSON converter và media type JSON. Không dùng **String.getBytes()** không tham số ở các điểm I/O nếu giao thức yêu cầu charset cố định; hãy truyền **StandardCharsets.UTF_8**.

### 6.4. Multipart upload

Với **multipart/form-data**, mỗi part có thể có header riêng. Giá trị filename trong **Content-Disposition** và dữ liệu text part chịu quy tắc khác nhau so với request body JSON. Không áp dụng một mẹo decode URL chung cho tên file, trường form và nội dung file.

Nếu upload file có tên Unicode, hãy kiểm thử client/proxy/container, sanitize tên file, không dùng tên file do người dùng gửi để ghép trực tiếp đường dẫn lưu trữ. Binary file bytes phải được bảo toàn; đừng tự decode mọi part như text UTF-8.

## 7. Ví dụ Spring Boot MVC chạy được: Unicode qua query, path và JSON

Ví dụ dưới đây giúp phân biệt ba đường dữ liệu. Dùng **Java 17+**, **Maven** và **Spring Boot 3.5.16** (một bản vá của dòng Boot 3.5). Máy chủ là embedded Tomcat từ **spring-boot-starter-web**.

### Cấu trúc dự án

~~~text
unicode-web-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/unicodeweb/
    │   ├── UnicodeWebApplication.java
    │   └── UnicodeController.java
    └── resources/
        └── application.yml
~~~

### pom.xml

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
    <artifactId>unicode-web-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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

### UnicodeWebApplication.java

~~~java
package com.example.unicodeweb;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UnicodeWebApplication {
    public static void main(String[] args) {
        SpringApplication.run(UnicodeWebApplication.class, args);
    }
}
~~~

### UnicodeController.java

~~~java
package com.example.unicodeweb;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/text")
public class UnicodeController {

    @GetMapping("/query")
    public Echo fromQuery(@RequestParam String value) {
        return new Echo(value);
    }

    @GetMapping("/path/{value}")
    public Echo fromPath(@PathVariable String value) {
        return new Echo(value);
    }

    @PostMapping(
        value = "/json",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Echo fromJson(@RequestBody Echo request) {
        return request;
    }

    public record Echo(String value) {
    }
}
~~~

Code dùng record **Echo** làm JSON DTO, thuận tiện kiểm tra giá trị String mà Spring MVC đã nhận. Với ứng dụng thực tế, cần validate dữ liệu người dùng và tránh trả lại trực tiếp dữ liệu nhạy cảm.

### application.yml

~~~yaml
server:
  port: 8080
  servlet:
    encoding:
      enabled: true
      charset: UTF-8
      force-request: true
      force-response: false
  tomcat:
    uri-encoding: UTF-8
~~~

### Chạy

Trong thư mục có pom.xml:

~~~bash
mvn spring-boot:run
~~~

Hoặc đóng gói:

~~~bash
mvn clean package
java -jar target/unicode-web-demo-1.0.0.jar
~~~

### Test 1: Query parameter có Unicode và ký tự reserved

~~~bash
curl -i --get \
  --data-urlencode "value=Cà phê & trà" \
  "http://localhost:8080/api/text/query"
~~~

Response body mong đợi về **giá trị**:

~~~json
{"value":"Cà phê & trà"}
~~~

Client **curl --data-urlencode** mã hóa đúng giá trị của query parameter; dấu **&** trở thành dữ liệu, không bị hiểu thành dấu phân tách parameter.

### Test 2: Path variable percent-encoded

~~~bash
curl -i "http://localhost:8080/api/text/path/Vi%E1%BB%87t"
~~~

Response body mong đợi:

~~~json
{"value":"Việt"}
~~~

Tomcat percent-decode URL theo UTF-8 và Spring MVC binding path variable đã được giải mã. Nếu sử dụng **%2F** trong một segment, kết quả còn phụ thuộc chính sách connector/proxy; không dùng nó làm bài kiểm thử Unicode thông thường.

### Test 3: JSON body có tiếng Việt và emoji

Tạo file **payload.json**, lưu thật sự bằng **UTF-8**:

~~~json
{"value":"Tiếng Việt 😀"}
~~~

Gửi request:

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  --data-binary @payload.json \
  "http://localhost:8080/api/text/json"
~~~

Response body biểu diễn cùng giá trị:

~~~json
{"value":"Tiếng Việt 😀"}
~~~

Một JSON serializer được cấu hình khác có thể escape Unicode thành chuỗi **\uXXXX**; nếu client parse ra đúng String thì vẫn là dữ liệu đúng. Để kiểm tra chính xác byte và Content-Type, dùng **curl -v**, dump response dưới dạng hex hoặc viết test nhận JSON và so sánh giá trị đã parse.

**Ghi chú shell:** các ví dụ curl nhiều dòng trên dùng cú pháp của Bash. Trên Windows PowerShell có thể dùng **curl.exe** trên một dòng, hoặc dùng continuation phù hợp; với JSON body, file UTF-8 giúp tránh sự khác nhau trong cách shell xử lý dấu nháy và Unicode.

## 8. Unicode normalization, so sánh và lưu trữ

Hai chuỗi nhìn giống nhau không nhất thiết có cùng dãy code point. Ví dụ **é** có thể là:

- Một code point **U+00E9** (dạng composed).
- Hai code point **U+0065 U+0301** (chữ e + combining acute accent).

Chương trình Java ở mục 5 minh họa **String.equals** trả false trước khi chuẩn hóa và true sau **Normalizer.Form.NFC**. Với tiếng Việt, các dấu thanh và dấu phụ cũng có thể có nhiều dạng kết hợp.

**Ứng dụng thực tế:**

- Với tên hiển thị, thường nên **giữ nguyên** chuỗi gốc nếu có giá trị hiển thị; chỉ chuẩn hóa khi nghiệp vụ yêu cầu.
- Với identifier, khóa so sánh hoặc giá trị cần unique, nên xác định chính sách chuẩn hóa (thường **NFC**) ở **cùng một ranh giới** trước khi lưu và so sánh. Áp dụng nhất quán cho create, lookup và update.
- **NFC** không giống **case folding**, xóa dấu hay chuyển chữ hoa/thường; không được trộn các thao tác này nếu nghiệp vụ không yêu cầu.
- **NFKC** có thể hợp nhất các ký tự tương thích và gây mất khác biệt có nghĩa; không dùng mặc định cho mọi dữ liệu người dùng.
- Các chuỗi trông giống nhau có thể là những ký tự Unicode khác hẳn nhau (homoglyph/confusable); chỉ NFC không giải quyết hết vấn đề phishing hoặc bảo mật identifier.

### 8.1. Đếm ký tự trong Java

**String.length()** đếm **UTF-16 code units**, không phải số Unicode code point, số chữ ghép hoặc số byte UTF-8. Một emoji có thể có nhiều code point (emoji + skin tone, zero-width joiner) và nhiều UTF-16 code units.

Nếu cần giới hạn độ dài cho giao diện hoặc cơ sở dữ liệu, phải quy định rõ giới hạn đang đo **byte**, **code point**, hay **grapheme cluster** (ký tự mà người dùng nhìn thấy). Không áp dụng cùng một giới hạn cho cả ba mà không kiểm thử.

### 8.2. File, database, log và API downstream

Unicode có thể bị hỏng **sau** khi đã qua controller đúng:

- **File text**: đọc/ghi bằng charset xác định, ví dụ **Files.readString(path, StandardCharsets.UTF_8)** và **Files.writeString(path, text, StandardCharsets.UTF_8)**.
- **Database**: dùng database/driver/cột có hỗ trợ đầy đủ Unicode và collation phù hợp. Ví dụ khi dùng MySQL, chú ý loại charset **utf8mb4** và so sánh theo collation; không suy rằng mọi cột tên **utf8** đều chứa được mọi emoji.
- **Logs**: kiểm tra encoding của appender, terminal, container runtime và hệ thống thu thập log. Chuỗi đúng trong JVM vẫn có thể hiển thị sai tại console.
- **HTTP client**: dùng message converter và URI builder phù hợp cho RestClient, WebClient hoặc SDK; kiểm tra charset request body và cách encode URL.
- **HTML/JSP**: cần đúng HTTP Content-Type charset, HTML metadata và encoding file template, tránh trộn JSP defaults với quy tắc JSON.

Nếu lỗi chỉ xảy ra ở một tầng, hãy kiểm tra **byte gốc**, **header Content-Type**, **chuỗi đã parse** và **đầu ra lưu trữ** ở điểm đó trước khi sửa cấu hình toàn hệ thống.

## 9. Đánh giá khi có reverse proxy, API gateway hoặc CDN

Một hệ thống production có thể có nhiều tầng:

~~~text
Browser / Mobile App
        |
        v
CDN / WAF / API Gateway
        |
        v
Reverse Proxy / Ingress
        |
        v
Embedded Tomcat
        |
        v
Spring MVC Controller
~~~

Một request URI có thể bị từ chối hoặc biến đổi **trước khi đến Tomcat**. Những điểm cần thống nhất:

1. Reverse proxy có **giữ nguyên** hay **decode/re-encode** URI?
2. Có từ chối encoded slash (**%2F**), encoded backslash, NUL hoặc percent escape không hợp lệ không?
3. Gateway có chuẩn hóa path hoặc chữ hoa/thường không?
4. Các tầng có cùng cách xử lý dấu cộng (**+**) ở query/form không?
5. Các header như **Content-Type** và các byte body có được chuyển nguyên vẹn không?
6. Luồng redirect và link generation có dùng URI builder để encode dữ liệu người dùng không?

**An toàn:** không tự động bật **server.tomcat.relaxed-path-chars**, **server.tomcat.relaxed-query-chars** hoặc cơ chế cho phép encoded slash để né lỗi 400/404. Cần kiểm tra URL được tạo đúng và đánh giá sự thống nhất giữa proxy và ứng dụng, vì các tầng decode khác nhau có thể gây path traversal, cache inconsistency hoặc bỏ qua kiểm soát truy cập.

## 10. Bộ kiểm thử nên có

Chỉ một request tiếng Việt thành công chưa đủ chứng minh toàn bộ web runtime xử lý Unicode đúng. Nên chạy ma trận tối thiểu:

| Input | Query | Path | JSON body | Form body |
|---|---|---|---|---|
| **Hà Nội** | Kiểm tra | Kiểm tra | Kiểm tra | Kiểm tra |
| **Cà phê & trà** | Kiểm tra encode & | Kiểm tra encode segment | Kiểm tra | Kiểm tra encode +/& |
| **A+B** | Kiểm tra %2B | Kiểm tra plus | Kiểm tra | Kiểm tra %2B |
| **日本語** | Kiểm tra | Kiểm tra | Kiểm tra | Kiểm tra |
| **😀** | Kiểm tra | Kiểm tra | Kiểm tra | Kiểm tra |
| **e + dấu kết hợp** | Kiểm tra NFC/NFD | Kiểm tra NFC/NFD | Kiểm tra NFC/NFD | Kiểm tra NFC/NFD |
| **a/b, a?b, a#b, a%b** | Kiểm tra reserved chars | Đánh giá chính sách path | Kiểm tra | Kiểm tra reserved chars |

Mỗi test nên kiểm tra:

- HTTP **status** đúng; không xuất hiện 400/404/415/500 ngoài mong đợi.
- **Content-Type** đúng media type, và charset khi loại media yêu cầu.
- Giá trị Unicode **sau khi parse** giống dữ liệu mong đợi.
- Dấu cách, **+**, **&**, **=**, **#**, **%** được xử lý như dữ liệu nếu đã encode trong đúng thành phần.
- Chuỗi kết hợp Unicode được so sánh theo chính sách ứng dụng; không âm thầm biến mất dấu.
- Nếu lỗi là do proxy, có thể tái lập khác biệt khi gọi trực tiếp backend so với gọi qua gateway.

Đối với API JSON, viết integration test dùng **MockMvc** hoặc **WebTestClient** sẽ ổn định hơn so sánh raw JSON bytes. Ví dụ cần dùng JSON parser để kiểm tra field **value**, thay vì so sánh định dạng escape trong response.

## 11. Chẩn đoán lỗi encoding phổ biến

| Hiện tượng | Nguyên nhân khả dĩ | Hướng kiểm tra và sửa |
|---|---|---|
| **Tiáº¿ng Viá»‡t** thay vì **Tiếng Việt** | UTF-8 bị đọc như charset khác | Kiểm tra raw bytes, Content-Type, charset tại điểm parse |
| Query tiếng Việt sai, JSON body đúng | URI decoding hoặc client encode URL sai | Kiểm tra percent-encoded URI, Tomcat URIEncoding, proxy |
| Ký tự **+** bị biến thành dấu cách | Giá trị form/query dùng dấu cộng chưa encode | Gửi **%2B** nếu là dấu cộng thật |
| **&** làm mất một phần parameter | Client tự nối query string không encode | Dùng URI builder hoặc --data-urlencode |
| URL path trả **400** với **%2F** | Encoded slash bị connector/proxy chặn theo chính sách | Thiết kế identifier không cần slash trong path; kiểm tra proxy |
| URL trả **404** dù controller tồn tại | Path đã bị decode thành segment khác hoặc có context path sai | Xem request-target thực tế và route mapping |
| Ký tự JSON bị escape thành **\uXXXX** | JSON serializer chọn biểu diễn escape | Parse JSON và so sánh Unicode String; không kết luận dữ liệu sai ngay |
| Emoji thành **?** khi ghi DB | Charset/collation/column hoặc connector DB không hỗ trợ | Kiểm tra schema, driver và encoding, thử round-trip |
| Chuỗi nhìn giống nhau nhưng **equals** false | Dạng Unicode normalization khác nhau | Áp dụng chính sách NFC/NFD ở boundary thích hợp |
| API đúng, console/log sai | Terminal hoặc log appender dùng encoding khác | Kiểm tra encoding file log, stdout và log collector |
| Form body sai dù đã đặt UTF-8 | Filter đã parse parameter trước khi charset được cấu hình | Xem thứ tự Servlet Filter, tránh parse request quá sớm |
| Đã đổi charset nhưng dữ liệu cũ vẫn sai | Byte đã bị giải mã sai và lưu dưới dạng mojibake | Xác định nguồn lỗi và cân nhắc quy trình sửa dữ liệu riêng |

**Không sửa lỗi bằng cách** encode toàn bộ String thành UTF-8 rồi lại decode với UTF-8 tại mọi tầng. Chỉ chuyển đổi **byte ↔ String** tại các ranh giới I/O cần thiết, và chỉ percent-encode khi xây dựng **URI component**.

## 12. Checklist triển khai an toàn

- [ ] Xác định Spring Boot version, Servlet hay WebFlux, server nhúng thực tế.
- [ ] Mặc định dùng UTF-8 cho body text; khai báo Content-Type chính xác.
- [ ] Với Spring MVC, kiểm tra **server.servlet.encoding.charset**, **force-request** và **force-response**.
- [ ] Với Tomcat, kiểm tra **server.tomcat.uri-encoding**; không nhầm với request-body charset.
- [ ] Dùng URI builder cho path/query, không dùng **URLEncoder** cho toàn bộ URL.
- [ ] Không double-encode hoặc double-decode phần URL do người dùng cung cấp.
- [ ] Giữ cấu hình decode nhất quán giữa reverse proxy và backend.
- [ ] JSON dùng UTF-8 theo RFC 8259; không phụ thuộc vào thêm charset parameter cho application/json.
- [ ] Đọc/ghi file text, kết nối database và log theo charset đã chọn.
- [ ] Xác định rõ khi nào cần Unicode normalization và so sánh chuỗi.
- [ ] Kiểm thử round-trip với tiếng Việt, CJK, emoji, dấu cộng, ampersand và kết hợp Unicode.
- [ ] Xử lý URI không hợp lệ/encoded slash theo chính sách bảo mật, không nới lỏng bừa bãi.

## 13. Tài liệu tham khảo

1. Spring Boot 3.5 – Common Application Properties (Servlet encoding và Tomcat URI encoding): https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
2. Spring Boot 3.5 – Servlet Web Applications, mục Character Encoding: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
3. Apache Tomcat 10.1 – HTTP Connector, thuộc tính URIEncoding và useBodyEncodingForURI: https://tomcat.apache.org/tomcat-10.1-doc/config/http.html
4. Spring Framework – URI Links, UriComponentsBuilder encoding: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-uri-building.html
5. RFC 3986 – Uniform Resource Identifier: https://www.rfc-editor.org/rfc/rfc3986
6. RFC 8259 – JSON encoding UTF-8 và media type: https://www.rfc-editor.org/rfc/rfc8259
7. Java 17 – Normalizer API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html
8. Java 17 – URLEncoder API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLEncoder.html

**Kết luận:** dữ liệu Unicode đi qua nhiều tầng độc lập. Đặt **UTF-8** cho request/response là cần thiết nhưng chưa đủ: **URI percent-encoding**, chính sách giải mã của **Tomcat/proxy**, HTTP message converter, Java String và dữ liệu lưu trữ đều phải phù hợp. Khi hiểu đúng mỗi ranh giới, bạn có thể xử lý tiếng Việt và Unicode ổn định mà không phải can thiệp mã hóa thủ công ở mọi nơi.
