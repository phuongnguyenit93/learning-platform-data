# PathPattern, quy tắc chọn ánh xạ cụ thể và lỗi ánh xạ trùng trong Spring MVC

## 1. Mục tiêu và phạm vi

Trong Spring MVC, một URL có thể khớp nhiều `@GetMapping` hoặc `@RequestMapping`. Framework phải kiểm tra toàn bộ điều kiện của request, so sánh độ cụ thể của các ánh xạ hợp lệ rồi chọn đúng một controller method. Bài này giúp bạn:

- Hiểu `PathPattern`, `PathPatternParser` và cách chúng so khớp từng đoạn (`path segment`) của URL.
- Phân biệt literal path, biến `{id}`, regex `{id:...}`, ký tự đại diện `?`, `*`, `**` và biến bắt phần đường dẫn còn lại `{*path}`.
- Dự đoán ánh xạ thắng khi nhiều endpoint cùng phù hợp; biết khi nào có lỗi `Ambiguous mapping` lúc khởi động hoặc `Ambiguous handler methods` khi nhận request.
- Viết route không chồng chéo ngoài ý muốn, kiểm chứng bằng HTTP request và `MockMvc`.

**Phạm vi:** controller dựa trên annotation trong **Spring MVC (Servlet stack)**, minh họa với Spring Framework 6.x / Spring Boot 3.x và Java 17+. Từ Spring MVC 6.0, parsed `PathPattern` là cơ chế khớp đường dẫn mặc định. Ứng dụng cũ có thể dùng `AntPathMatcher` do cấu hình/phiên bản khác; không áp nguyên xi mọi kết luận về cú pháp và thứ tự ưu tiên cho chế độ đó.

## 2. Từ request đến handler method

`@RequestMapping` tại class và method được kết hợp thành route hoàn chỉnh. Ví dụ, `@RequestMapping("/api/orders")` trên class cộng với `@GetMapping("/{id}")` trên method tạo endpoint `GET /api/orders/{id}`.

Luồng chọn handler, giản lược:

```text
HTTP request
  → DispatcherServlet
  → RequestMappingHandlerMapping
  → tìm RequestMappingInfo có các điều kiện phù hợp:
      đường dẫn, HTTP method, params, headers, consumes, produces, ...
  → nếu nhiều ứng viên: so sánh độ ưu tiên trong ngữ cảnh request
  → chọn handler tốt nhất nếu duy nhất
  → chuyển đổi @PathVariable, bind tham số, gọi controller method
```

`PathPatternParser` biên dịch các mẫu URL thành `PathPattern` và so sánh với đường dẫn request đã được phân tích (`RequestPath`/`PathContainer`). Việc xử lý từng đoạn đường dẫn giúp tránh một số rủi ro khi giải mã toàn bộ URL thành một chuỗi rồi mới so khớp. `PathPattern` là thành phần **khớp URL**, còn `RequestMappingInfo` bao gồm thêm HTTP method và các điều kiện request khác.

Hai điều cần tách bạch:

1. **Khớp hay không khớp:** một pattern có thể nhận request này và từ chối request khác. Chẳng hạn `/users/{id:[0-9]+}` không khớp `/users/alice`.
2. **Ai được chọn khi cùng khớp:** nếu cả `/users/current` và `/users/{id}` khớp `/users/current`, pattern literal được chọn. So khớp chỉ trả lời câu hỏi “ứng viên nào hợp lệ”; độ cụ thể quyết định thứ tự giữa chúng.

Tên tham số Java, thứ tự khai báo các method trong class, và thứ tự controller được quét **không phải** quy tắc ưu tiên route.

## 3. Đọc nhanh cú pháp PathPattern trước khi so độ cụ thể

Để so hai pattern cùng khớp, trước hết cần biết **mỗi pattern nhận được bao nhiêu path segment**. Với `PathPatternParser` của Spring MVC 6.x, đây là các dạng thiết yếu:

| Pattern | Phạm vi và giá trị capture |
| --- | --- |
| `/users/me` | Literal: chỉ nhận segment `me`. |
| `/users/{id}` | Nhận một segment, đặt giá trị vào biến `id`. |
| `/users/{id:[0-9]+}` | Một segment phải thỏa regex số; regex **giới hạn matching**, không tự tăng điểm ưu tiên khi hai pattern cùng match. |
| `/files/*.png`, `/files/a?.txt` | `*` và `?` chỉ khớp ký tự trong **một** segment (lần lượt nhiều ký tự và đúng một ký tự). |
| `/assets/**` | Catch-all không đặt tên, nhận nhiều segment ở **cuối** path. |
| `/assets/{*path}` | Catch-all có tên, ví dụ `/assets/css/app.css` cho biến `path=/css/app.css`. |

Không đặt `**` hay `{*path}` ở giữa pattern với `PathPatternParser`: `/a/**/b` là mẫu không hợp lệ. Query string không được tính là path segment, nên `?` trong URI request khác `?` trong pattern. Phân biệt thêm lỗi URL **không match regex** với lỗi conversion Java như `@PathVariable long id` không đọc được giá trị ngoài phạm vi `long`.

Phần quan trọng riêng của bài này không phải liệt kê thêm wildcard, mà là **so các ứng viên đã match**, lý giải vì sao literal thắng một biến, vì sao catch-all xếp sau, và phát hiện mapping trùng/không thể phân định. Hãy kiểm thử riêng vấn đề dấu slash cuối, encoding và reverse proxy trên cấu hình thực tế: Spring MVC 6.x mặc định không tự gộp `/users` với `/users/`, còn URL có `%2F` hoặc dấu `;` có thể chịu chính sách container/proxy/security trước khi đến handler.

## 4. So sánh độ cụ thể khi nhiều pattern đều khớp

Với parsed patterns, Spring dùng `PathPattern.SPECIFICITY_COMPARATOR` để sắp xếp các pattern phù hợp. Trực giác thiết kế là **literal chính xác trước, biến hoặc wildcard sau, catch-all cuối**.

Các nguyên tắc cốt lõi:

1. Pattern catch-all như `/**` và `/{*rest}` đứng sau những pattern không phải catch-all. Giữa các catch-all, pattern có phần tiền tố dài/cụ thể hơn thường được ưu tiên.
2. Với các pattern thông thường, Spring tính độ phức tạp dựa trên số biến URI và wildcard (biến `{x}`, dấu `*`, `?` tạo cơ sở so sánh theo các quy tắc parser). Mẫu có **điểm thấp hơn** cụ thể hơn.
3. Khi điểm bằng nhau, mẫu **dài hơn** được ưu tiên; nếu vẫn hòa, mẫu có **nhiều biến URI hơn wildcard** có thể thắng.
4. Nếu so sánh các ứng viên cuối cùng vẫn hòa và cùng khớp một request, Spring **không tùy tiện lấy method khai báo trước**: lỗi chọn handler do ánh xạ mơ hồ sẽ xuất hiện.

Ví dụ với request `GET /users/me`:

| Ứng viên | Khớp? | Diễn giải |
| --- | --- | --- |
| `/users/me` | Có | Literal trùng chính xác, cụ thể nhất |
| `/users/{id}` | Có | Biến một đoạn, tổng quát hơn literal |
| `/users/*` | Có | Wildcard trong một đoạn |
| `/users/**` | Có | Catch-all ở cuối, thấp ưu tiên hơn |
| `/teams/{id}` | Không | Khác tiền tố |

**Kết quả:** `/users/me` thắng. Nếu bỏ route literal, `/users/{id}` thường thắng `/users/*` khi các yếu tố khác hòa.

Không nên tự viết bộ máy phân giải dựa trên một câu “ít wildcard hơn là thắng” cho mọi trường hợp. Spring xét cả `RequestMappingInfo`: HTTP method, `params`, `headers`, `consumes`, `produces` và các điều kiện khác, rồi mới có thứ tự ưu tiên cuối. Một pattern đẹp cũng không thành ứng viên nếu HTTP method hoặc `Content-Type` của request không phù hợp.

### Những điều kiện khác ngoài path

```java
@RestController
@RequestMapping("/reports")
class ReportController {

    @GetMapping(params = "format=csv", produces = "text/csv")
    String csv() {
        return "id,name\n1,Ada\n";
    }

    @GetMapping(params = "format=json", produces = "application/json")
    String json() {
        return "{\"id\":1,\"name\":\"Ada\"}";
    }

    @PostMapping(consumes = "application/json")
    String create(@RequestBody String payload) {
        return "accepted";
    }
}
```

*Đoạn trên minh họa cách khai báo các điều kiện mapping; đưa vào ứng dụng Spring MVC có các import/bootstrapping tương ứng.* Hai method GET cùng `/reports` nhưng khác `params` và `produces` nên không phải ánh xạ trùng hệt nhau. Ví dụ `GET /reports?format=csv` kèm `Accept: text/csv` chọn `csv()`; `POST /reports` kèm `Content-Type: application/json` chọn `create()`.

Phân biệt `@GetMapping(params = "format=csv")` với `@RequestParam String format`: thuộc tính `params` là **điều kiện chọn mapping**; `@RequestParam` chủ yếu phục vụ **bind/kiểm tra tham số sau khi handler đã được chọn**. Tương tự, `@PathVariable long id` không làm route tự ưu tiên “số” hơn route nhận `String`. Muốn chặn chữ ngay trong khâu khớp URL, dùng regex trong pattern hoặc tạo đường dẫn literal khác nhau.

Nếu đường dẫn tồn tại nhưng HTTP method không được hỗ trợ, mặc định Spring MVC thường phản hồi `405 Method Not Allowed`. Sai `Content-Type` so với `consumes` có thể dẫn đến `415 Unsupported Media Type`, `Accept` không phù hợp với `produces` có thể dẫn đến `406 Not Acceptable`; điều kiện `params` không được đáp ứng có thể dẫn đến `400 Bad Request`. Path không có mapping thường là `404 Not Found`. Các handler ngoại lệ, bộ lọc bảo mật và cấu hình ứng dụng có thể thay đổi kết quả quan sát.

## 5. Ví dụ ứng dụng chạy được với Java 17 và Spring Boot 3

Tạo project Maven như sau (Spring Boot 3.3.13 dùng ở đây làm phiên bản minh họa cố định cho Spring Framework 6.x):

```text
path-pattern-demo/
├── pom.xml
└── src/
    ├── main/java/example/PathPatternDemoApplication.java
    └── test/java/example/ProductRoutesControllerTest.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>path-pattern-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
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
```

File `src/main/java/example/PathPatternDemoApplication.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PathPatternDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PathPatternDemoApplication.class, args);
    }
}

@RestController
@RequestMapping("/api/products")
class ProductRoutesController {

    @GetMapping("/featured")
    String featured() {
        return "featured";
    }

    @GetMapping("/{id:\\d+}")
    String byId(@PathVariable("id") long id) {
        return "id:" + id;
    }

    @GetMapping("/{slug:[a-z][a-z0-9-]*}")
    String bySlug(@PathVariable("slug") String slug) {
        return "slug:" + slug;
    }

    @GetMapping("/files/{*path}")
    String file(@PathVariable("path") String path) {
        return "file:" + path;
    }
}
```

Lệnh thực thi với **JDK 17+ và Maven** đã được cài đặt:

```bash
mvn test
mvn spring-boot:run
```

Ở terminal khác, gửi các request sau:

```bash
curl -s http://localhost:8080/api/products/featured
curl -s http://localhost:8080/api/products/42
curl -s http://localhost:8080/api/products/blue-mug
curl -s http://localhost:8080/api/products/files/guide/intro.pdf
```

Mỗi lệnh trả về đúng body tương ứng (mỗi body không tự thêm ký tự xuống dòng):

```text
featured
id:42
slug:blue-mug
file:/guide/intro.pdf
```

Giải thích:

- `/api/products/featured` đồng thời khớp literal và mẫu slug, nhưng literal thắng.
- `/api/products/42` chỉ khớp mẫu `{id:\\d+}` trong hai mẫu `id`/`slug`; binding `long` diễn ra sau khi route đã chọn.
- `/api/products/blue-mug` khớp mẫu slug; không khớp biểu thức số.
- `/api/products/files/guide/intro.pdf` được bắt bởi `{*path}` trong route con `/files`. Mẫu slug không thể hấp thụ nhiều đoạn đường dẫn.

Với cấu hình mặc định của ví dụ, `GET /api/products/42/` có dấu slash cuối không khớp `GET /api/products/42`; `POST /api/products/42` có thể trả `405` vì chỉ khai báo GET. Khi kiểm thử bằng `curl -i`, hãy xem mã HTTP ngoài body để phân biệt 404, 405 và lỗi điều kiện mapping.

## 6. Hai kiểu lỗi ánh xạ trùng rất khác nhau

### 6.1. Lỗi ngay lúc khởi động: hai handler có ánh xạ đồng nhất

**Ví dụ cố ý sai** dưới đây là một controller thay thế, **không** thêm nó vào project đang chạy ở mục 5:

```java
@RestController
@RequestMapping("/api/duplicate")
class DuplicateController {

    @GetMapping("/{id}")
    String first(@PathVariable String id) {
        return "first";
    }

    @GetMapping("/{id}")
    String second(@PathVariable String id) {
        return "second";
    }
}
```

Cả hai method đăng ký cùng `RequestMappingInfo` (HTTP GET, `/api/duplicate/{id}`, không khác điều kiện nào khác). Khi tạo registry cho các controller, `RequestMappingHandlerMapping` phát hiện xung đột và có thể ném `IllegalStateException` với nội dung liên quan `Ambiguous mapping`/`Cannot map ... There is already ... mapped`. Ứng dụng không khởi động hoàn tất.

Cách xử lý: bỏ endpoint trùng, gộp logic vào một method, hoặc thiết kế lại hợp đồng HTTP để các ánh xạ thực sự khác nhau về đường dẫn/method/điều kiện có ý nghĩa. Đổi **tên Java method** hoặc tên tham số `@PathVariable` nhưng giữ nguyên annotation mapping không giải quyết trường hợp trùng hệt.

### 6.2. Lỗi lúc nhận request: hai mẫu khác nhau nhưng ưu tiên ngang nhau

**Ví dụ cố ý sai**, cũng không thêm vào project đang chạy:

```java
@RestController
@RequestMapping("/api/ambiguous")
class AmbiguousController {

    @GetMapping("/{id}")
    String byId(@PathVariable String id) {
        return "id:" + id;
    }

    @GetMapping("/{slug}")
    String bySlug(@PathVariable String slug) {
        return "slug:" + slug;
    }
}
```

Hai chuỗi pattern `/{id}` và `/{slug}` không giống hệt nhau về tên biến, nên có thể được đăng ký thành hai mapping riêng. Nhưng với `GET /api/ambiguous/123`, **cả hai đều khớp một đoạn**, đều có mức cụ thể tương đương và không có điều kiện nào để phân định. Spring MVC không biết chọn method nào, dẫn tới `IllegalStateException` với thông điệp dạng `Ambiguous handler methods mapped for '/api/ambiguous/123'` khi request đến. Kết quả HTTP thường là 500 nếu không có xử lý ngoại lệ tùy chỉnh.

**Điểm dễ nhầm:** đặt `@PathVariable long id` ở method thứ nhất và `@PathVariable String slug` ở method thứ hai không giải quyết xung đột: chuyển đổi đối số Java chỉ xảy ra sau lựa chọn handler. Việc thêm một regex vào một route cũng chưa chắc tạo ra “độ ưu tiên tuyệt đối” nếu cả hai vẫn cùng khớp; tránh trùng tập URL hoặc định danh route rõ ràng.

Hai cách sửa hợp lý:

```java
// Phương án A: phân biệt URL rõ ràng.
@GetMapping("/by-id/{id}")
String byId(@PathVariable long id) { return "id:" + id; }

@GetMapping("/by-slug/{slug}")
String bySlug(@PathVariable String slug) { return "slug:" + slug; }

// Phương án B: regex có hai tập giá trị tách biệt.
@GetMapping("/{id:\\d+}")
String numericId(@PathVariable long id) { return "id:" + id; }

@GetMapping("/{slug:[a-z][a-z-]*}")
String alphabeticSlug(@PathVariable String slug) { return "slug:" + slug; }
```

*Đây là hai phương án thay thế để đưa vào một controller phù hợp, không phải bốn method cần khai báo đồng thời.*

Nếu tên slug có thể chỉ gồm chữ số (ví dụ `"123"`), hãy xác định quy tắc sản phẩm: ưu tiên dành namespace riêng cho ID/slug thay vì để hai route tranh một URL. Không dựa vào thứ tự code để “vá” ánh xạ mơ hồ.

### 6.3. Checklist chẩn đoán

1. Xác định lỗi xảy ra **trong quá trình startup** hay **chỉ khi gọi một URL**. Startup thường chỉ ra mapping trùng; request-time thường là các mẫu khác nhau nhưng có cùng độ ưu tiên đối với URL cụ thể.
2. Ghi đầy đủ method + path + query string + `Content-Type` + `Accept` + các header liên quan. Đừng kiểm tra mỗi URL.
3. Mở phần mapping của hai handler trong stack trace; cộng prefix ở class với path ở method để so sánh URL cuối cùng.
4. Kiểm tra wildcard và biến có thể nhận cùng một path; đặc biệt `/{id}` vs `/{slug}`, regex chồng lấp, `*` và catch-all.
5. Xem danh sách mappings đã đăng ký (ví dụ endpoint `/actuator/mappings` khi ứng dụng có Spring Boot Actuator và cho phép truy cập) hoặc bật log phù hợp cho `RequestMappingHandlerMapping`.
6. Viết test cho những URL ở vùng giao nhau và cả những URL lẽ ra không được khớp; sửa thiết kế đường dẫn/điều kiện rồi chạy lại.

## 7. Kiểm thử route bằng MockMvc

File `src/test/java/example/ProductRoutesControllerTest.java` (phù hợp với project ở mục 5):

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProductRoutesController.class)
class ProductRoutesControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void literalBeatsVariableAndRegexSeparatesIdsFromSlugs() throws Exception {
        mvc.perform(get("/api/products/featured"))
                .andExpect(status().isOk())
                .andExpect(content().string("featured"));

        mvc.perform(get("/api/products/42"))
                .andExpect(status().isOk())
                .andExpect(content().string("id:42"));

        mvc.perform(get("/api/products/blue-mug"))
                .andExpect(status().isOk())
                .andExpect(content().string("slug:blue-mug"));
    }

    @Test
    void catchAllOnlyAppliesUnderFilesPrefix() throws Exception {
        mvc.perform(get("/api/products/files/guide/intro.pdf"))
                .andExpect(status().isOk())
                .andExpect(content().string("file:/guide/intro.pdf"));

        mvc.perform(get("/api/products/42/"))
                .andExpect(status().isNotFound());

        mvc.perform(post("/api/products/42"))
                .andExpect(status().isMethodNotAllowed());
    }
}
```

Chạy `mvn test`. Các assertion này kiểm tra **handler thực sự được chọn** bằng body, đồng thời kiểm tra trailing slash và method. Với sản phẩm thực tế, bổ sung các trường hợp `params`, `headers`, `consumes`, `produces` và những request có khả năng khớp hai route.

Để tránh test “xanh” giả khi ứng dụng có security, filter, servlet path hoặc cấu hình MVC bổ sung, hãy kết hợp `MockMvc` với một số bài kiểm tra tích hợp chạy trên cấu hình triển khai thực tế. Nếu test tình huống cố ý ambiguous, tách riêng controller lỗi vào test context của nó; không đặt nó trong cùng ứng dụng demo vì có thể khiến context không khởi động.

## 8. Các lỗi tư duy thường gặp và cách phòng tránh

| Nhầm lẫn | Điều đúng hơn |
| --- | --- |
| “Định nghĩa `@GetMapping` trước thì nó thắng.” | Spring so điều kiện và độ cụ thể, không lấy thứ tự source code làm hợp đồng. |
| “`/{id}` và `/{slug}` khác nhau nên chắc chắn không xung đột.” | Hai tên biến khác nhau vẫn khớp cùng một tập path một đoạn; request có thể mơ hồ. |
| “`@PathVariable Long id` làm mapping chỉ nhận số.” | Type conversion diễn ra sau chọn route; để lọc đường dẫn cần regex hoặc phân biệt prefix. |
| “Có regex hẹp hơn luôn thắng biến tổng quát.” | Regex giới hạn việc **khớp**; khi cả hai cùng khớp, phải xét comparator, không suy đoán theo ngữ nghĩa regex. |
| “`*` khớp mọi cấp thư mục.” | `*` ở trong một đoạn; `**`/`{*path}` mới bắt nhiều đoạn và phải ở cuối. |
| “Thêm `/**` ở mọi nơi là an toàn.” | Catch-all dễ làm route thiếu rõ ràng; chỉ dùng khi cần và kiểm thử các path biên. |
| “`GET /a` luôn giống `GET /a/`.” | Spring MVC 6.x mặc định không tự nối trailing slash. |
| “`@RequestParam` tự phân biệt hai `@GetMapping` cùng path.” | Cần điều kiện mapping `params=...` nếu muốn dùng query parameter để chọn handler. |
| “Mọi request không vào controller đều là 404.” | 405/400/406/415 hoặc lỗi bảo mật/bind có thể xuất hiện tùy điều kiện và cấu hình. |

**Quy tắc thiết kế thực dụng:** ưu tiên đường dẫn literal có ý nghĩa; đặt namespace khác nhau cho hai loại tài nguyên dễ chồng lấp; dùng regex để giới hạn biến khi thật sự xác định được miền giá trị; tránh catch-all rộng; bảo đảm mỗi request dự kiến có một handler thắng duy nhất. Đối với hệ thống đã public API, kiểm tra tương thích URL trước khi đổi đường dẫn.

## 9. Tự kiểm tra

1. Với ba mapping GET `/shop/new`, `/shop/{sku}` và `/shop/**`, `GET /shop/new` chọn ai? **Đáp án:** `/shop/new` vì literal cụ thể hơn.
2. `/files/*` có khớp `/files/icons/logo.svg` không? **Không**, vì `*` chỉ trong một segment.
3. Nếu cùng tồn tại `GET /people/{id}` và `GET /people/{name}`, vì sao `GET /people/7` có thể lỗi khi chạy? **Hai pattern cùng khớp, cùng độ cụ thể**, trong khi tên biến không phân biệt giá trị.
4. Thêm `@PathVariable Long id` có chữa được câu 3? **Không**; phải sửa hợp đồng URL hoặc ràng buộc pattern không giao nhau.
5. Hai method cùng `@GetMapping("/sync")` không điều kiện khác nhau gây lỗi lúc nào? **Khi đăng ký mapping lúc khởi động**, thường có lỗi `Ambiguous mapping`.
6. Vì sao `POST /api/products/42` không vào method GET dù path trùng? **HTTP method** là một phần của `RequestMappingInfo`; với cấu hình demo Spring MVC sẽ phản hồi 405.

## 10. Tài liệu gốc để tra cứu

- [Spring Framework — Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): URI patterns, chọn pattern cụ thể và các điều kiện mapping.
- [Spring Framework — Servlet Path Matching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/handlermapping-path.html): parsed `RequestPath`, `PathPatternParser`, khác biệt với `AntPathMatcher` và xử lý URL encoding.
- [PathPatternParser API (Spring 6.2)](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/util/pattern/PathPatternParser.html): mặc định case-sensitive và trailing slash.
- [RequestMappingInfo API (Spring 6.2)](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/RequestMappingInfo.html): tập điều kiện dùng để nhận diện, lọc và so sánh mapping.
