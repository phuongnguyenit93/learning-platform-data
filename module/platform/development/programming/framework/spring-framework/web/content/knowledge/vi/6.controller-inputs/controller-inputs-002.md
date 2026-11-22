# Spring MVC: @RequestParam — tham số bắt buộc, giá trị mặc định, nhiều giá trị và Map

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận dữ liệu đầu vào của controller bằng `@RequestParam` và phân biệt tham số bắt buộc với tham số tùy chọn.
- Đặt `defaultValue`, hiểu khi nào giá trị mặc định được dùng và Spring chuyển đổi kiểu dữ liệu như thế nào.
- Nhận nhiều giá trị cùng tên qua mảng hoặc `List<T>`.
- Thu thập toàn bộ request parameters bằng `Map<String, String>` hoặc `MultiValueMap<String, String>`, chọn đúng cấu trúc khi key có thể xuất hiện nhiều lần.
- Chẩn đoán lỗi thường gặp (thiếu tham số, chuyển đổi kiểu sai, giá trị rỗng) và kiểm thử endpoint thực tế.

Phạm vi: Spring MVC (Servlet stack), Java 17+; ví dụ chạy bằng Spring Boot 3.5.0 và Spring Framework 6.2.x. Các hành vi cốt lõi bên dưới cũng được mô tả trong tài liệu Spring MVC.

## 2. @RequestParam nhận dữ liệu nào?

`@RequestParam` ánh xạ **request parameter** sang một tham số của phương thức controller:

~~~java
@GetMapping("/hello")
public String hello(@RequestParam("name") String name) {
    return "Hello " + name;
}
~~~

Với yêu cầu `GET /hello?name=Lan`, biến `name` nhận `"Lan"`.

Trong **Spring MVC**, khái niệm request parameter của Servlet bao gồm query string (ví dụ `?page=2`) và dữ liệu form được Servlet phân tích (thường là `application/x-www-form-urlencoded`). Đối với JSON trong request body, sử dụng `@RequestBody` với kiểu DTO phù hợp; đối với một đoạn URL như `/products/42`, sử dụng `@PathVariable`. Spring WebFlux có quy tắc khác: `@RequestParam` chỉ lấy query parameters; không chuyển nguyên tắc MVC này sang WebFlux một cách máy móc.

**Cơ chế tóm lược:** Spring tìm request parameter theo tên → xác định có bị thiếu hay không → dùng giá trị mặc định nếu được cấu hình → chuyển đổi chuỗi sang kiểu Java đích → gọi phương thức controller. Các lỗi ở giai đoạn phân giải đối số có thể trả HTTP 400 trước khi phần thân phương thức chạy.

## 3. Thuộc tính của @RequestParam

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `name` / `value` | Tên request parameter; hai thuộc tính là bí danh của nhau | `@RequestParam("q")`, `@RequestParam(name = "q")` |
| `required` | Mặc định `true`: phải có tham số; `false`: cho phép vắng mặt | `@RequestParam(name = "q", required = false)` |
| `defaultValue` | Giá trị thay thế khi tham số **vắng mặt hoặc có giá trị rỗng**; tự động khiến `required` không còn bắt buộc | `@RequestParam(name = "page", defaultValue = "0")` |

Nên ghi rõ `name` trong ví dụ và API công khai. Nếu bỏ tên, việc suy ra tên từ tham số Java phụ thuộc thông tin tên tham số có sẵn khi biên dịch; tên tường minh cũng giúp API dễ đọc.

### 3.1. Tham số bắt buộc

~~~java
@GetMapping("/search")
public String search(@RequestParam(name = "q") String q) {
    return "Searching: " + q;
}
~~~

- `GET /search?q=java` → `q = "java"`.
- `GET /search` → thiếu `q`, Spring MVC mặc định trả HTTP **400 Bad Request**, thường với `MissingServletRequestParameterException`.
- `GET /search?q=` → `q` có mặt nhưng là chuỗi rỗng. Với `String` và không có ràng buộc kiểm tra nội dung, `required = true` **không đồng nghĩa** “không được để trống”.

Nếu nghiệp vụ đòi hỏi chữ có nghĩa, hãy bổ sung kiểm tra đầu vào (ví dụ Bean Validation với `@NotBlank` và cấu hình validation phù hợp) hoặc logic kiểm tra riêng. Đừng dùng `required` thay cho validation.

### 3.2. Không bắt buộc: required = false và Optional

~~~java
@GetMapping("/filter")
public String filter(
        @RequestParam(name = "category", required = false) String category,
        @RequestParam(name = "minPrice") Optional<Integer> minPrice) {
    String selected = category == null ? "all" : category;
    String lowerBound = minPrice.map(String::valueOf).orElse("none");
    return selected + " / " + lowerBound;
}
~~~

Khi thiếu `category`, đối số tham chiếu thường nhận `null`; khi thiếu `minPrice`, `Optional<Integer>` là `Optional.empty()`. Dùng `Optional` có thể biểu diễn ý nghĩa “có hoặc không có” rõ hơn. Tránh dựa vào `null` với kiểu nguyên thủy như `int`: hãy chọn `Integer`, `Optional<Integer>` hoặc cung cấp giá trị mặc định.

### 3.3. Giá trị mặc định

~~~java
@GetMapping("/page")
public String page(
        @RequestParam(name = "page", defaultValue = "0") int page,
        @RequestParam(name = "size", defaultValue = "20") int size) {
    return "page=" + page + ", size=" + size;
}
~~~

| URL | `page` | `size` | Lý do |
| --- | ---: | ---: | --- |
| `/page` | 0 | 20 | Cả hai vắng mặt |
| `/page?page=3` | 3 | 20 | Chỉ `size` dùng mặc định |
| `/page?page=&size=5` | 0 | 5 | Chuỗi rỗng kích hoạt `defaultValue` |
| `/page?page=abc` | — | — | Không đổi `abc` thành `int` được; thông thường HTTP 400 |

`defaultValue` là chuỗi trong annotation; Spring chuyển đổi nó sang kiểu khai báo (`"20"` → `int 20`). Khai báo đồng thời `required = true` và `defaultValue` gây hiểu nhầm vì **có mặc định là không bắt buộc**. Giá trị mặc định không có tác dụng thay thế mọi giá trị không hợp lệ: `?page=abc` không “rơi về 0”.

## 4. Nhiều giá trị của cùng một tham số

Một URL có thể lặp lại cùng key:

~~~text
GET /api/tags?tag=java&tag=spring&tag=web
~~~

Nhận bằng mảng hoặc danh sách:

~~~java
@GetMapping("/tags")
public List<String> tags(@RequestParam(name = "tag") List<String> tags) {
    return tags;
}

@GetMapping("/tag-array")
public String[] tagArray(@RequestParam(name = "tag") String[] tags) {
    return tags;
}
~~~

Với URL trên, kết quả biểu diễn ba phần tử `["java", "spring", "web"]`. Nếu khai báo `List<Integer>`, Spring còn phải chuyển đổi từng giá trị sang số; một phần tử như `tag=abc` có thể làm binding thất bại. Với `List<String>` bắt buộc, thiếu hẳn tham số `tag` có thể gây HTTP 400; để cho phép vắng mặt:

~~~java
@GetMapping("/tags-optional")
public List<String> tagsOptional(
        @RequestParam(name = "tag", required = false) List<String> tags) {
    return tags == null ? List.of() : tags;
}
~~~

Khi khách hàng gửi một chuỗi ngăn cách bằng dấu phẩy (`?tag=java,spring`), Spring có thể phân tách trong quá trình chuyển đổi kiểu tùy dạng dữ liệu và cấu hình. Để API không mơ hồ, hãy **quy ước rõ** cách gửi danh sách; các ví dụ ở đây dùng key lặp lại. Không giả định mọi client hoặc converter đều xử lý cú pháp dấu phẩy giống nhau.

## 5. Map và MultiValueMap

### 5.1. Thu tất cả parameters với Map<String, String>

~~~java
@GetMapping("/params")
public Map<String, String> params(@RequestParam Map<String, String> params) {
    return params;
}
~~~

Yêu cầu `/params?name=Lan&sort=asc` tạo map có `name → "Lan"`, `sort → "asc"`. Điểm quyết định: **không ghi tên** trong `@RequestParam` và kiểu đối số là `Map<String, String>`, Spring thu các request parameters theo tên vào map. Mỗi key trong map chỉ lưu được **một** chuỗi; khi một key xuất hiện nhiều lần, cấu trúc này không giữ được đầy đủ các giá trị lặp lại.

### 5.2. Thu đầy đủ giá trị lặp lại với MultiValueMap<String, String>

~~~java
import org.springframework.util.MultiValueMap;

@GetMapping("/params-all")
public MultiValueMap<String, String> paramsAll(
        @RequestParam MultiValueMap<String, String> params) {
    return params;
}
~~~

Với `/params-all?tag=java&tag=spring&sort=asc`, dữ liệu tương đương:

~~~json
{
  "tag": ["java", "spring"],
  "sort": ["asc"]
}
~~~

`MultiValueMap<K, V>` biểu diễn một key → `List<V>`. Dùng `getFirst("tag")` nếu chỉ muốn giá trị đầu tiên, `get("tag")` khi muốn toàn bộ danh sách. Chú ý import chính xác `org.springframework.util.MultiValueMap`.

| Kiểu tham số controller | Chọn khi nào | Nếu gửi `?tag=a&tag=b` |
| --- | --- | --- |
| `@RequestParam("tag") String tag` | API cần một giá trị | Không phù hợp để bảo toàn mọi giá trị |
| `@RequestParam("tag") List<String> tags` | Chỉ cần mọi giá trị của riêng key `tag` | `["a", "b"]` |
| `@RequestParam Map<String, String> params` | Muốn toàn bộ tên tham số, một giá trị/key | Không bảo toàn cả `a` và `b` |
| `@RequestParam MultiValueMap<String, String> params` | Muốn toàn bộ tên và mọi giá trị/key | `tag → ["a", "b"]` |

**Cẩn thận với tên annotation:** `@RequestParam("filters") Map<...>` không có nghĩa “thu toàn bộ parameters vào map”. Khi chỉ rõ tên `filters`, Spring tìm một parameter có tên đó và tìm cách chuyển đổi **giá trị của riêng parameter ấy** thành `Map` (cần bộ chuyển đổi thích hợp). Để gom tất cả key, dùng `@RequestParam Map<String, String>` **không chỉ rõ tên**.

## 6. Ví dụ chạy được với Java 17 và Spring Boot

Cấu trúc dự án Maven:

~~~text
request-param-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── RequestParamDemoApplication.java
~~~

Tạo `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>request-param-demo</artifactId>
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

Tạo `src/main/java/demo/RequestParamDemoApplication.java`:

~~~java
package demo;

import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.util.MultiValueMap;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class RequestParamDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RequestParamDemoApplication.class, args);
    }
}

@RestController
@RequestMapping("/api")
class ParamController {
    @GetMapping("/required")
    public Map<String, String> required(@RequestParam("q") String q) {
        return Map.of("q", q);
    }

    @GetMapping("/defaults")
    public Map<String, Integer> defaults(
            @RequestParam(name = "page", defaultValue = "0") int page,
            @RequestParam(name = "size", defaultValue = "20") int size) {
        return Map.of("page", page, "size", size);
    }

    @GetMapping("/optional")
    public Map<String, Object> optional(
            @RequestParam(name = "keyword", required = false) String keyword,
            @RequestParam(name = "limit") Optional<Integer> limit) {
        return Map.of(
                "keyword", keyword == null ? "(none)" : keyword,
                "limit", limit.orElse(10));
    }

    @GetMapping("/tags")
    public Map<String, List<String>> tags(
            @RequestParam(name = "tag", required = false) List<String> tags) {
        return Map.of("tags", tags == null ? List.of() : tags);
    }

    @GetMapping("/map")
    public Map<String, String> map(@RequestParam Map<String, String> all) {
        return all;
    }

    @GetMapping("/multi")
    public MultiValueMap<String, String> multi(
            @RequestParam MultiValueMap<String, String> all) {
        return all;
    }
}
~~~

Ở thư mục chứa `pom.xml`, chạy:

~~~bash
mvn spring-boot:run
~~~

Ứng dụng mặc định lắng nghe trên `http://localhost:8080`. Có thể thử:

~~~bash
curl -i 'http://localhost:8080/api/required?q=java'
curl -i 'http://localhost:8080/api/required'
curl -i 'http://localhost:8080/api/defaults?page=&size=5'
curl -i 'http://localhost:8080/api/defaults?page=oops'
curl -i 'http://localhost:8080/api/optional'
curl -i 'http://localhost:8080/api/tags?tag=java&tag=spring'
curl -i 'http://localhost:8080/api/map?name=Lan&sort=asc'
curl -i 'http://localhost:8080/api/multi?tag=java&tag=spring&sort=asc'
~~~

Nếu chạy trong Windows PowerShell và `curl` là alias, dùng `curl.exe`.

Đối chiếu kết quả quan trọng (thứ tự key trong JSON object không được bảo đảm):

| Lệnh/đường dẫn | Kết quả chính |
| --- | --- |
| `/api/required?q=java` | HTTP 200, `{"q":"java"}` |
| `/api/required` | HTTP 400 do thiếu `q` |
| `/api/defaults?page=&size=5` | HTTP 200, `page=0`, `size=5` |
| `/api/defaults?page=oops` | HTTP 400 vì `oops` không chuyển thành `int` |
| `/api/optional` | HTTP 200, `keyword="(none)"`, `limit=10` |
| `/api/tags?tag=java&tag=spring` | HTTP 200, `{"tags":["java","spring"]}` |
| `/api/map?name=Lan&sort=asc` | HTTP 200, map chứa `name="Lan"`, `sort="asc"` |
| `/api/multi?tag=java&tag=spring&sort=asc` | HTTP 200, `tag=["java","spring"]`, `sort=["asc"]` |

Các chuỗi phản hồi lỗi mặc định (body, message, trace) có thể khác theo cấu hình Spring Boot; kiểm tra HTTP status và dữ liệu trả về thay vì phụ thuộc thông điệp lỗi nguyên văn.

## 7. Những lỗi dễ mắc và cách xử lý

1. **Tưởng `required = true` đồng nghĩa phải có chữ:** Với `String`, `?q=` vẫn là chuỗi rỗng. Kiểm tra tính hợp lệ ở tầng validation.
2. **Cho rằng `defaultValue` sửa được mọi đầu vào sai:** `?page=abc` thường là lỗi chuyển đổi số, không biến thành giá trị mặc định.
3. **Dùng `int` với `required = false` mà không có mặc định:** Kiểu nguyên thủy không chứa `null`; dùng `Integer`, `Optional<Integer>` hoặc `defaultValue`.
4. **Dùng `Map<String, String>` để nhận mọi giá trị trùng key:** Cần `MultiValueMap<String, String>` hoặc `List<String>`.
5. **Ghi `@RequestParam("x") Map<String, String>` để gom tất cả:** Tên `x` khiến Spring xử lý một parameter được đặt tên, không phải mọi parameters.
6. **Nhầm request parameters với JSON body hoặc path variable:** Chọn đúng `@RequestBody`, `@PathVariable`, `@RequestParam` theo nguồn dữ liệu.
7. **Tin dữ liệu Map có thể dùng trực tiếp vào truy vấn hoặc bộ lọc:** Mọi key/value từ client đều không đáng tin. Với API nghiêm ngặt, dùng tham số/DTO đã định nghĩa, validate giá trị, giới hạn trang/kích thước và whitelist tên sort/filter trước khi dùng.
8. **Không chuẩn hóa cách client gửi danh sách:** Quy định rõ key lặp lại, mã hóa URL hợp lệ, tên key chính xác; dùng `curl --get --data-urlencode` khi giá trị chứa khoảng trắng hoặc ký tự đặc biệt.

## 8. Tự luyện tập

**Bài 1 — Required:** Viết `GET /orders?id=12` nhận `long id`. Điều gì xảy ra khi bỏ `id` hoặc gửi `id=xyz`? Giải thích hai nguyên nhân khác nhau dẫn tới HTTP 400.

**Bài 2 — Default:** Viết `GET /products?page=1&size=10` với mặc định `page=0`, `size=20`. Dự đoán `/products?page=&size=7` và đề xuất giới hạn hợp lệ cho `size`.

**Bài 3 — Multi-value:** Nhận `?color=red&color=blue` thành `List<String>`. Sửa endpoint để không lỗi khi thiếu `color`; trả danh sách rỗng.

**Bài 4 — Map:** Với `?tag=a&tag=b&sort=asc`, nêu sự khác nhau giữa `Map<String,String>` và `MultiValueMap<String,String>`. Cho biết cách lấy riêng phần tử đầu tiên của `tag` từ `MultiValueMap`.

*Gợi ý kiểm tra:* Bài 1 phân biệt thiếu parameter và chuyển đổi `String → long` sai; bài 2 `page=0`, `size=7`; bài 3 dùng `required=false` rồi thay `null` bằng `List.of()`; bài 4 dùng `params.get("tag")` và `params.getFirst("tag")`.

## 9. Tài liệu tham khảo

- [Spring Framework — MVC `@RequestParam`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html): cách bind request parameters, `Optional`, mảng/list, `Map` và `MultiValueMap`.
- [Spring Framework — `RequestParam` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/annotation/RequestParam.html): ý nghĩa chính xác của `name`, `required` và `defaultValue`.
- [Spring Boot 3.5.0 release](https://spring.io/blog/2025/05/22/spring-boot-3-5-0-available-now/): phiên bản dùng trong dự án ví dụ.
