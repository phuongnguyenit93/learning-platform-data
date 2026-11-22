# @PathVariable và @MatrixVariable trong đường dẫn — Spring MVC

> **Phạm vi:** Spring MVC trên Servlet stack, ví dụ Java 17+ và Spring Boot dùng `spring-boot-starter-web`. Bài này giải thích cách lấy dữ liệu từ **phần đường dẫn URL**, cách phân biệt biến chiếm chỗ với tham số theo từng đoạn đường dẫn, và những điều kiện để matrix variable hoạt động an toàn.

## 1. Nhìn vào URL trước khi viết controller

Xét ba HTTP request:

```text
GET /api/orders/42
GET /api/cars/7;color=red,green;year=2012
GET /api/owners/42;q=11/pets/21;q=22
```

- Trong `/orders/42`, `42` thay thế chỗ trống `{orderId}` trong route `/orders/{orderId}`: dùng `@PathVariable` để nhận mã đơn hàng.
- Trong `/cars/7;color=red,green;year=2012`, đoạn đường dẫn có giá trị chính `7` và metadata `color`, `year` nằm sau dấu chấm phẩy `;`: `@PathVariable` nhận `7`; `@MatrixVariable` nhận `color` và `year`.
- Trong `/owners/42;q=11/pets/21;q=22`, tên `q` xuất hiện ở **hai đoạn** khác nhau. `@MatrixVariable(pathVar = "...")` chỉ định chính xác đoạn cần đọc.

| Annotation | Dữ liệu lấy từ đâu? | Ví dụ | Giá trị |
| --- | --- | --- | --- |
| `@PathVariable("orderId")` | Biến `{orderId}` trong mẫu đường dẫn | `/orders/42` | `42` |
| `@MatrixVariable("color")` | Cặp `key=value` sau dấu `;` trong một path segment | `/cars/7;color=red` | `red` |
| `@RequestParam("color")` | Query string sau `?` | `/cars/7?color=red` | `red` |

**Ghi nhớ:** `@PathVariable` định danh tài nguyên hoặc thành phần của route; `@MatrixVariable` mô tả tham số gắn với một **đoạn đường dẫn cụ thể**. Chúng có thể dùng cùng nhau trong một phương thức xử lý.

## 2. `@PathVariable`: ánh xạ URI template vào tham số Java

### 2.1. Khai báo route, đặt tên rõ ràng

```java
@RestController
@RequestMapping("/api")
class OrderController {

    @GetMapping("/orders/{orderId}")
    public String findOrder(@PathVariable("orderId") long orderId) {
        return "orderId=" + orderId;
    }
}
```

- `@GetMapping("/orders/{orderId}")` đăng ký mẫu URL; dấu ngoặc nhọn khai báo biến của đường dẫn.
- `@PathVariable("orderId")` lấy giá trị ứng với `{orderId}`. `long` yêu cầu Spring chuyển chuỗi `42` thành số.
- `GET /api/orders/42` trả nội dung `orderId=42`.
- `GET /api/orders/abc` khớp mẫu route nhưng không chuyển được `abc` thành `long`, thông thường trả HTTP **400 Bad Request** do lỗi chuyển kiểu.
- `GET /api/orders` thiếu đoạn bắt buộc `/{orderId}` nên không khớp mapping trên, thông thường trả HTTP **404 Not Found** nếu không có route khác.

Có thể bỏ tên trong `@PathVariable` nếu tên tham số Java khớp tên biến route và thông tin tên tham số được lưu lúc biên dịch (ví dụ `-parameters`). Viết rõ `@PathVariable("orderId")` giúp tránh phụ thuộc thiết lập biên dịch và dễ đọc khi tên Java khác URI.

### 2.2. Lấy nhiều biến và ghép mapping lớp/phương thức

```java
@RestController
@RequestMapping("/owners/{ownerId}")
class PetController {

    @GetMapping("/pets/{petId}")
    public String getPet(
            @PathVariable("ownerId") long ownerId,
            @PathVariable("petId") long petId) {
        return "ownerId=" + ownerId + ", petId=" + petId;
    }
}
```

Request `GET /owners/42/pets/21` trả `ownerId=42, petId=21`. `{ownerId}` ở mapping cấp lớp vẫn được method đọc như bình thường.

Nếu cần lấy mọi URI template variable mà không khai báo từng tham số, có thể dùng `@PathVariable Map<String, String> variables`; tuy nhiên, tên cụ thể và kiểu dữ liệu rõ ràng thường dễ kiểm tra, bảo trì hơn.

### 2.3. Ràng buộc mẫu URI và kiểu dữ liệu

```java
@GetMapping("/versions/{version:v[0-9]+}")
public String version(@PathVariable("version") String version) {
    return version;
}
```

Route trên khớp `/versions/v12` và không khớp `/versions/latest`. Mẫu `{version:v[0-9]+}` là **điều kiện khớp URL**, còn annotation `@PathVariable` chỉ nhận giá trị đã trích ra. Với `@PathVariable UUID id` hoặc `long id`, chuyển kiểu được thực hiện bằng hệ thống conversion của Spring MVC. Regex không thay thế kiểm tra nghiệp vụ, quyền truy cập hoặc xác thực tài nguyên.

Trong Spring MVC hiện đại, `PathPatternParser` xử lý đường dẫn theo từng segment. `{id}` thông thường bắt một đoạn; ký tự `/` phân chia các đoạn. Khi cần bắt nhiều đoạn cuối, Spring còn có cú pháp `{*path}` nhưng chỉ dùng ở vị trí thích hợp theo quy tắc `PathPattern`, tránh giả định rằng `{id}` sẽ tự nhận mọi ký tự `/`.

## 3. `@MatrixVariable`: tham số `;key=value` gắn với path segment

Một **path segment** là phần nằm giữa hai dấu `/`. Matrix variable xuất hiện ngay trong segment đó, sau dấu `;`:

```text
/cars/7;color=red;year=2012
      └── segment: "7;color=red;year=2012"
          ├── path variable carId = "7"
          ├── matrix variable color = "red"
          └── matrix variable year = "2012"
```

Mẫu mapping nên có URI variable che phần segment mang tham số, chẳng hạn `/cars/{carId}`:

```java
@GetMapping("/cars/{carId}")
public String getCar(
        @PathVariable("carId") long carId,
        @MatrixVariable(name = "color", pathVar = "carId") String color,
        @MatrixVariable(name = "year", pathVar = "carId") int year) {
    return "carId=" + carId + ", color=" + color + ", year=" + year;
}
```

Với `GET /cars/7;color=red;year=2012`, kết quả là:

```text
carId=7, color=red, year=2012
```

`name` (hoặc `value`) chọn tên tham số; `pathVar` chọn URI template variable của **segment chứa nó**. Nếu chỉ có một segment mang matrix variable và không mơ hồ, có thể bỏ `pathVar`. Khi nhiều segment cùng chứa tên giống nhau, hãy chỉ định `pathVar` rõ ràng.

### 3.1. Hai cách truyền nhiều giá trị

Spring MVC hỗ trợ nhiều giá trị phân tách bằng dấu phẩy hoặc lặp lại cùng key:

```text
/cars/7;color=red,green;year=2012
/cars/7;color=red;color=green;year=2012
```

Có thể nhận `color` dưới dạng `List<String>` (qua cơ chế chuyển đổi giá trị mặc định của Spring) hoặc dùng `MultiValueMap<String, String>` để giữ nguyên các giá trị theo từng tên. Ví dụ nhận một tham số:

```java
@GetMapping("/cars/{carId}")
public List<String> carColors(
        @MatrixVariable(name = "color", pathVar = "carId") List<String> colors) {
    return colors;
}
```

Với `/cars/7;color=red,green`, body JSON tương ứng là:

```json
["red","green"]
```

Đoạn code trên **minh họa một method controller riêng**, không khai báo đồng thời với một method khác có cùng `@GetMapping("/cars/{carId}")` trong cùng ứng dụng; nếu trùng mapping, Spring có thể báo ambiguous mapping khi khởi động.

### 3.2. Phân biệt cùng tên trên các segment

```java
@GetMapping("/owners/{ownerId}/pets/{petId}")
public String getPet(
        @PathVariable("ownerId") long ownerId,
        @PathVariable("petId") long petId,
        @MatrixVariable(name = "q", pathVar = "ownerId") int ownerQ,
        @MatrixVariable(name = "q", pathVar = "petId") int petQ) {
    return "ownerId=" + ownerId + ", petId=" + petId
            + ", ownerQ=" + ownerQ + ", petQ=" + petQ;
}
```

Request:

```text
GET /owners/42;q=11/pets/21;q=22
```

Trả về:

```text
ownerId=42, petId=21, ownerQ=11, petQ=22
```

`pathVar = "ownerId"` đọc `q=11` từ segment `42;q=11`; `pathVar = "petId"` đọc `q=22` từ segment `21;q=22`. Không nên dựa vào việc Spring chọn ngẫu nhiên một giá trị khi cùng tên xuất hiện nhiều chỗ.

### 3.3. Tùy chọn, giá trị mặc định và bản đồ tham số

Mặc định `@MatrixVariable` có `required = true`. Khi tham số vắng mặt, Spring MVC thông thường trả 400 vì không giải quyết được tham số bắt buộc.

```java
@GetMapping("/pets/{petId}")
public String petDetail(
        @PathVariable("petId") long id,
        @MatrixVariable(name = "lang", pathVar = "petId",
                        defaultValue = "vi") String lang,
        @MatrixVariable(name = "page", pathVar = "petId",
                        defaultValue = "1") int page) {
    return "id=" + id + ", lang=" + lang + ", page=" + page;
}
```

Với `/pets/21`, giá trị là `id=21, lang=vi, page=1`. `defaultValue` cũng khiến tham số không còn bắt buộc. Nếu chọn `required = false` mà **không** có `defaultValue`, nên dùng kiểu tham chiếu `Integer` thay vì `int` để biểu diễn thiếu giá trị rõ ràng.

Để đọc toàn bộ matrix variables thay vì một key:

```java
@GetMapping("/owners/{ownerId}/pets/{petId}")
public MultiValueMap<String, String> allPetParameters(
        @MatrixVariable(pathVar = "petId")
        MultiValueMap<String, String> petParameters) {
    return petParameters;
}
```

Đoạn method minh họa này cần `import org.springframework.util.MultiValueMap;`. Request `/owners/42;q=11/pets/21;q=22;s=23` cho map của segment `petId` với `q → ["22"]`, `s → ["23"]`. Nếu bỏ `pathVar` trên `MultiValueMap`, Spring có thể gom matrix variables từ các segment của route; chẳng hạn `q` có hai giá trị `11` và `22`. Cần dùng `MultiValueMap` khi có khả năng lặp key; `Map<String, String>` chỉ biểu diễn một giá trị mỗi key.

## 4. Spring MVC xử lý hai annotation như thế nào?

1. `DispatcherServlet` nhận request và tìm handler qua `RequestMappingHandlerMapping` theo HTTP method và pattern đã đăng ký.
2. Engine match đường dẫn xác định template variables (ví dụ `ownerId=42`, `petId=21`) và dữ liệu matrix gắn với từng segment nếu đường dẫn, cấu hình và tầng bảo mật cho phép.
3. `HandlerMethodArgumentResolver` thích hợp xử lý `@PathVariable`, `@MatrixVariable`; `ConversionService` chuyển giá trị chuỗi thành `long`, `int`, collection, kiểu tùy biến khi được cấu hình.
4. Spring gọi method controller với các đối số; `@RestController` chuyển giá trị trả về thành HTTP response body thông qua message converter.

Mô hình tư duy: **pattern chọn handler → các resolver lấy dữ liệu URL → conversion chuyển kiểu → method xử lý nghiệp vụ**. Annotation không tự thực hiện truy vấn cơ sở dữ liệu hoặc xác thực quyền truy cập tài nguyên.

## 5. Ví dụ hoàn chỉnh có thể chạy — Java 17 + Spring Web

Tạo project Spring Boot trên [Spring Initializr](https://start.spring.io/) với Java 17 trở lên và dependency **Spring Web**. Dùng đúng package `com.example.demo`, thay nội dung file `src/main/java/com/example/demo/DemoApplication.java` bằng toàn bộ đoạn sau. Đây là **một chương trình đầy đủ** (ba endpoint không trùng mapping):

```java
package com.example.demo;

import java.util.List;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.MatrixVariable;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@RestController
@RequestMapping("/api")
class RouteController {

    @GetMapping("/orders/{orderId}")
    public String order(@PathVariable("orderId") long orderId) {
        return "orderId=" + orderId;
    }

    @GetMapping("/cars/{carId}")
    public String car(
            @PathVariable("carId") long carId,
            @MatrixVariable(name = "color", pathVar = "carId",
                            required = false) List<String> colors,
            @MatrixVariable(name = "year", pathVar = "carId",
                            defaultValue = "0") int year) {
        List<String> safeColors = colors == null ? List.of() : colors;
        return "carId=" + carId
                + ", colors=" + safeColors
                + ", year=" + year;
    }

    @GetMapping("/owners/{ownerId}/pets/{petId}")
    public String pet(
            @PathVariable("ownerId") long ownerId,
            @PathVariable("petId") long petId,
            @MatrixVariable(name = "q", pathVar = "ownerId") int ownerQ,
            @MatrixVariable(name = "q", pathVar = "petId") int petQ) {
        return "ownerId=" + ownerId
                + ", petId=" + petId
                + ", ownerQ=" + ownerQ
                + ", petQ=" + petQ;
    }
}
```

Từ thư mục gốc dự án đã sinh bằng Spring Initializr, chạy Maven wrapper:

```bash
# macOS/Linux
./mvnw spring-boot:run

# Windows PowerShell hoặc Command Prompt
mvnw.cmd spring-boot:run
```

Các lệnh cURL sau sử dụng URL đặt trong dấu nháy để shell không diễn giải dấu `;`. Trên Windows PowerShell, thay `curl` bằng `curl.exe` nếu `curl` được ánh xạ sang lệnh khác:

```bash
curl -s 'http://localhost:8080/api/orders/42'
# orderId=42

curl -s 'http://localhost:8080/api/cars/7;color=red,green;year=2012'
# carId=7, colors=[red, green], year=2012

curl -s 'http://localhost:8080/api/cars/7'
# carId=7, colors=[], year=0

curl -s 'http://localhost:8080/api/owners/42;q=11/pets/21;q=22'
# ownerId=42, petId=21, ownerQ=11, petQ=22
```

Các dòng `# ...` là **kết quả body dự kiến**, không phải một phần stdout của ứng dụng Java. `curl -s` in body không kèm status; nếu cần phân tích HTTP status/header dùng `curl -i`. Kết quả matrix variable giả định các tầng HTTP và bảo mật thực sự cho phép dấu `;` đi đến Spring MVC; xem mục 6 trước khi kết luận controller lỗi.

## 6. Cấu hình và bảo mật: nguyên nhân phổ biến khiến matrix variable không chạy

### 6.1. Khác biệt engine khớp đường dẫn

Spring MVC 6.0+ mặc định dùng **`PathPatternParser`**: parser tách path theo segment, xử lý path parameters phục vụ trích matrix variables; thông thường không cần cấu hình legacy `UrlPathHelper` chỉ để đọc matrix data.

Một số ứng dụng Spring MVC cũ dùng **`AntPathMatcher`** (string pattern matching). Với cấu hình legacy này, nếu `UrlPathHelper` xóa nội dung sau dấu `;`, `@MatrixVariable` không còn dữ liệu để lấy. Các bài hướng dẫn cũ thường cấu hình:

```java
// Chỉ minh họa cho ứng dụng MVC dùng cơ chế legacy AntPathMatcher.
@Override
public void configurePathMatch(PathMatchConfigurer configurer) {
    UrlPathHelper helper = new UrlPathHelper();
    helper.setRemoveSemicolonContent(false);
    configurer.setUrlPathHelper(helper);
}
```

Đây là **đoạn method cấu hình minh họa**, cần đặt trong lớp `@Configuration implements WebMvcConfigurer` với các import thích hợp. Không sao chép máy móc vào cấu hình Spring MVC 6+/7+ hiện đại, vì cách khớp đường dẫn và tính tương thích khác nhau. Nếu dùng legacy, trước tiên xác minh cấu hình matcher hiện hành.

### 6.2. Spring Security thường chặn dấu chấm phẩy

`StrictHttpFirewall` của Spring Security mặc định **từ chối semicolon trong URL** do rủi ro HTTP request ambiguity và bypass quy tắc bảo mật. Điều này có thể gây lỗi trước khi request đi vào controller, dù `@MatrixVariable` và mapping viết đúng. Nếu ứng dụng thật sự cần matrix parameters và đã đánh giá rủi ro, tài liệu Spring Security đưa ra ví dụ:

```java
// Đoạn cấu hình độc lập; yêu cầu spring-security-web trên classpath.
@Bean
StrictHttpFirewall httpFirewall() {
    StrictHttpFirewall firewall = new StrictHttpFirewall();
    firewall.setAllowSemicolon(true);
    return firewall;
}
```

Import `org.springframework.context.annotation.Bean` và `org.springframework.security.web.firewall.StrictHttpFirewall` trong lớp cấu hình Security. **Chỉ bật khi thực sự cần**; sau đó phải kiểm thử các quy tắc authorization, URL normalization, proxy, cache và giới hạn tham số. Với Spring Security, đây là thay đổi chính sách bảo mật, không phải bước bắt buộc chung của Spring MVC. Khi `spring-boot-starter-web` chạy đơn lẻ mà không thêm Spring Security, ví dụ ở mục 5 không cần bean này.

### 6.3. Proxy, gateway và client

Dấu `;` có thể bị reverse proxy, server, firewall hoặc client xử lý theo các quy tắc riêng. Hãy xem **request thực sự mà controller nhận được** khi gỡ lỗi, kiểm tra gateway và container. Không đặt access token, mật khẩu, dữ liệu bí mật vào cả path, matrix parameter hay query string vì URL có thể xuất hiện trong log, lịch sử trình duyệt và bộ nhớ đệm. Với API công khai có yêu cầu tương thích rộng, `?color=red&year=2012` cùng `@RequestParam` thường dễ vận hành hơn.

## 7. Phân biệt và chọn cách thiết kế endpoint

| Nhu cầu | Đề xuất | Ví dụ |
| --- | --- | --- |
| Xác định một tài nguyên cụ thể | `@PathVariable` | `GET /orders/42` |
| Xác định tài nguyên lồng nhau | Nhiều `@PathVariable` | `GET /owners/42/pets/21` |
| Filter/sort/pagination chung của tài nguyên danh sách | `@RequestParam` | `GET /cars?color=red&page=2` |
| Metadata có ngữ nghĩa **theo từng segment** | `@MatrixVariable`, nếu hạ tầng hỗ trợ | `GET /owners/42;q=11/pets/21;q=22` |

Đừng dùng `@MatrixVariable` để thay thế `@PathVariable` cho ID; cũng đừng giả định `@RequestParam` có thể đọc `;color=red`. Mỗi annotation lấy dữ liệu từ một vị trí khác nhau của URL.

Một lựa chọn thiết kế dễ bảo trì thường là route rõ định danh + query parameters cho bộ lọc. Matrix variables hữu ích khi cần diễn đạt tùy chọn gắn với **một đoạn cụ thể** của tuyến đường; chi phí là yêu cầu hỗ trợ nhất quán của client, gateway và tầng bảo mật.

## 8. Lỗi thường gặp và cách khoanh vùng

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| `404` với `/orders` | Mapping yêu cầu `/{orderId}` | Gọi đúng URL hoặc khai báo route riêng cho collection |
| `400` với `/orders/abc` | `abc` không chuyển được sang `long` | Dùng ID hợp lệ hoặc chọn kiểu `String` kèm kiểm tra |
| `400` khi thiếu `;color=...` | `@MatrixVariable` mặc định bắt buộc | Dùng `required=false` hoặc `defaultValue` |
| `q` sai/không rõ thuộc segment nào | Cùng tên matrix variable ở nhiều segment | Dùng `pathVar="ownerId"` hoặc `pathVar="petId"` |
| Có `;` thì request bị từ chối sớm | Spring Security `StrictHttpFirewall` hoặc proxy/container | Xác định lớp chặn; chỉ đổi chính sách sau khi đánh giá rủi ro |
| Không đọc được matrix param dù route khớp | Parser/cấu hình legacy đã loại nội dung `;...` | Kiểm tra MVC path matching mode và `UrlPathHelper` nếu dùng legacy |
| Lỗi `Name for argument ... not specified` | Bỏ tên annotation và không giữ parameter names khi compile | Viết rõ `@PathVariable("id")` / `@MatrixVariable("color")` |
| Lỗi ambiguous mapping lúc khởi động | Hai method khai báo cùng HTTP method + route | Chỉ giữ một handler cho một mapping tương đương |

Thực hành gỡ lỗi: (1) thử route đơn giản `/api/orders/42`, (2) gọi matrix route với `curl -i`, (3) kiểm tra status và log Spring Security/proxy, (4) xác nhận có đúng URI template variable bao lấy segment, (5) đối chiếu tên `pathVar` và kiểu dữ liệu Java. Tránh sửa cấu hình bảo mật như một phản xạ khi chưa xác định tầng gây lỗi.

## 9. Tự kiểm tra kiến thức

**Câu 1.** Với `@GetMapping("/books/{id}")` và `@PathVariable("id") Long id`, URL `/books/50` cho `id` bằng gì? Nếu gọi `/books/abc` thì điều gì có thể xảy ra?

**Đáp án:** `id=50L` sau chuyển kiểu; `abc` không chuyển sang `Long` nên thông thường Spring MVC trả 400.

**Câu 2.** Với `/owners/42;view=compact/pets/21;view=full`, làm sao đọc `view=full` một cách rõ ràng?

```java
@MatrixVariable(name = "view", pathVar = "petId") String view
```

Method mapping tương ứng phải có `/owners/{ownerId}/pets/{petId}`, và trong ví dụ `view` nhận `full`.

**Câu 3.** `/cars/7;color=red` và `/cars/7?color=red` khác ở đâu?

**Đáp án:** Trường hợp đầu là matrix variable thuộc path segment `7`; trường hợp sau là query parameter, thường dùng `@RequestParam("color")`.

**Câu 4.** Vì sao `@MatrixVariable` không đọc được trong ứng dụng có Spring Security dù method đúng?

**Đáp án:** Một khả năng đáng kiểm tra là `StrictHttpFirewall` từ chối URL chứa `;` trước bước mapping. Thay đổi cấu hình cần cân nhắc rủi ro bảo mật và xem xét lựa chọn query parameters.

## 10. Tài liệu chuẩn để tra cứu

- [Spring Framework — Mapping Requests / URI patterns](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): `@PathVariable`, pattern, regexp, chuyển kiểu.
- [Spring Framework — Matrix Variables](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/matrix-variables.html): cú pháp `;name=value`, `pathVar`, `defaultValue`, `MultiValueMap`.
- [Spring Framework — Servlet Path Matching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/handlermapping-path.html): `PathPatternParser` và khác biệt matching.
- [Spring Security — HttpFirewall](https://docs.spring.io/spring-security/reference/servlet/exploits/firewall.html): mặc định chặn semicolon và chính sách ngoại lệ.
- [Spring Framework — Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html): vị trí các annotation trong hệ thống resolver.

**Tổng kết vận dụng:** dùng `@PathVariable` cho thành phần được đặt tên bằng mẫu URI, dùng `@MatrixVariable` khi cần đọc các cặp `key=value` gắn với từng segment, chỉ rõ `pathVar` khi có nhiều đoạn, và kiểm tra tầng bảo mật/hạ tầng trước khi đưa dấu `;` vào hợp đồng API.
