# Đặt đường dẫn tài liệu và cache headers

## 1. Mục tiêu

Trong module **SPRING_REST_DOCS**, test HTTP dùng MockMvc, WebTestClient hoặc REST Assured sinh snippet cho request, response, payload, header, parameter và multipart part. Asciidoctor/Markdown ghép snippet thành tài liệu REST API. Khi tài liệu được đóng gói và phục vụ như static resources, cần thiết kế URL ổn định và cache policy phù hợp để người dùng truy cập đúng phiên bản mà không giữ nội dung cũ quá lâu.

Bài học giải quyết ba câu hỏi: tài liệu được truy cập qua URL nào; HTML, CSS, JavaScript, ảnh và font nên có Cache-Control khác nhau ra sao; và làm thế nào kiểm tra cache headers, conditional requests cùng nội dung sau release.

## 2. Tách URL công khai khỏi classpath location

Giả sử JAR chứa:

```text
BOOT-INF/classes/static/docs/
├── index.html
├── css/site.css
├── js/navigation.js
└── images/upload-flow.png
```

Classpath path là `static/docs/index.html`. Với static resource mapping mặc định, URL thường là `/docs/index.html`; prefix `static` không xuất hiện trong URL.

| Thành phần | Giá trị |
| --- | --- |
| Classpath location | `classpath:/static/docs/` |
| File entry point | `index.html` |
| URL mặc định | `/docs/index.html` |
| CSS URL | `/docs/css/site.css` |
| Image URL | `/docs/images/upload-flow.png` |

Không suy đoán URL public từ tên thư mục. Nếu ứng dụng đổi `spring.mvc.static-path-pattern`, context path hoặc đăng ký resource handler riêng thì URL thực tế sẽ khác.

## 3. Đặt URL prefix bằng ResourceHandlerRegistry

Khi cần prefix rõ ràng như `/api-reference/**`, ánh xạ prefix tới classpath docs:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class ApiDocsWebConfiguration implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/api-reference/**")
                .addResourceLocations("classpath:/static/docs/");
    }
}
```

Mapping tương ứng:

| Resource | URL |
| --- | --- |
| `static/docs/index.html` | `/api-reference/index.html` |
| `static/docs/css/site.css` | `/api-reference/css/site.css` |
| `static/docs/images/upload-flow.png` | `/api-reference/images/upload-flow.png` |

Resource location nên kết thúc bằng dấu slash. Prefix URL có thể khác tên thư mục classpath. Kiểm tra MVC configuration để custom handler không ảnh hưởng static resources khác.

### 3.1. URL entry point thân thiện

Dùng URL tường minh `/api-reference/index.html` là cách dễ kiểm chứng. Không mặc định `/api-reference/` luôn tự mở index trong thư mục con; welcome-page handling phụ thuộc cấu hình/version.

Nếu muốn URL ngắn, tạo redirect có chủ đích:

```java
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
class ApiDocsLandingController {

    @GetMapping("/api-reference")
    String redirectToDocs() {
        return "redirect:/api-reference/index.html";
    }
}
```

Xác minh redirect location khi ứng dụng chạy với context path hoặc reverse proxy.

## 4. Chọn chiến lược version URL

Tài liệu API thay đổi theo release. Các chiến lược phổ biến:

| Chiến lược | Ví dụ | Phù hợp |
| --- | --- | --- |
| URL ổn định trỏ bản mới nhất | `/api-reference/index.html` | Người dùng muốn docs hiện hành |
| URL có version | `/api-reference/v1/index.html` | Giữ docs của API version cũ |
| URL theo release | `/api-reference/2026.11/index.html` | Truy vết chính xác tài liệu đã phát hành |

Có thể cung cấp cả URL ổn định cho bản hiện hành và URL versioned cho các release được hỗ trợ. URL versioned cần bất biến sau khi phát hành.

Ví dụ:

```text
static/
└── api-reference/
    ├── current/index.html
    ├── v1/index.html
    └── v2/index.html
```

Nếu chỉ phát hành docs cùng một JAR, package version hiện hành. Nếu cần giữ nhiều phiên bản, cân nhắc publish docs như artifact/site riêng để không mang toàn bộ lịch sử vào mọi JAR.

Version trong URL cần tương ứng version API/release do team công bố. Không xóa version cũ khi vẫn còn client cần tra cứu.

## 5. Cache-Control và các directive cơ bản

Header `Cache-Control` hướng dẫn browser và shared cache cách lưu và tái sử dụng response.

| Directive | Ý nghĩa |
| --- | --- |
| `max-age=300` | Có thể dùng response trong 300 giây mà không revalidate |
| `public` | Shared cache được phép lưu response nếu các điều kiện khác cho phép |
| `private` | Chỉ private cache như browser của người dùng được lưu |
| `no-cache` | Có thể lưu nhưng phải revalidate trước khi dùng lại |
| `no-store` | Không lưu response trong cache |
| `must-revalidate` | Khi response stale, phải xác minh lại trước khi dùng |
| `immutable` | Trong thời gian còn fresh, client không cần revalidate tài nguyên đó |

`no-cache` không có nghĩa là không lưu; muốn cấm lưu dùng `no-store`. `private` không thay thế authorization. `public` không làm endpoint private trở nên an toàn để chia sẻ.

### 5.1. HTML và assets có vòng đời khác nhau

HTML landing page thường thay đổi theo release. CSS/JS/ảnh có thể cache lâu nếu tên file chứa hash/version và nội dung không đổi dưới cùng URL.

| Loại tài nguyên | Policy gợi ý | Lý do |
| --- | --- | --- |
| `index.html` ở URL current | `no-cache` hoặc max-age ngắn | Cần revalidate để nhận release mới |
| HTML versioned bất biến | max-age dài, có thể immutable | URL đại diện một bản cố định |
| CSS/JS tên cố định | max-age ngắn/vừa | Nội dung có thể đổi tại cùng URL |
| CSS/JS có hash/version | max-age dài + immutable | URL thay đổi khi nội dung thay đổi |
| Ảnh/font versioned | max-age dài + immutable | Asset không đổi dưới cùng URL |
| Tài liệu private | private hoặc no-store | Tránh shared cache giữ nội dung nhạy cảm |

Đây là policy mẫu; thời gian cụ thể phụ thuộc tần suất release và CDN. Không gắn immutable cho `/docs/index.html` nếu URL luôn trỏ tới bản mới nhất.

## 6. Cấu hình cache bằng ResourceHandlerRegistry

Spring MVC cho phép đặt CacheControl trên resource handler:

```java
import java.time.Duration;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class ApiDocsResourceConfiguration implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/api-reference/**")
                .addResourceLocations("classpath:/static/docs/")
                .setCacheControl(CacheControl.maxAge(Duration.ofMinutes(5))
                        .cachePublic());
    }
}
```

Ví dụ cho phép cache công khai trong 5 phút. Chỉ dùng `cachePublic()` nếu nội dung thực sự public. Với docs cần đăng nhập hoặc chứa thông tin nội bộ, dùng policy private/no-store và authorization phù hợp.

### 6.1. Policy khác nhau cho HTML và asset

Có thể đăng ký handler với pattern cụ thể:

```java
registry.addResourceHandler("/api-reference/**/*.html")
        .addResourceLocations("classpath:/static/docs/")
        .setCacheControl(CacheControl.noCache());

registry.addResourceHandler("/api-reference/assets/**")
        .addResourceLocations("classpath:/static/docs/assets/")
        .setCacheControl(CacheControl.maxAge(Duration.ofDays(365))
                .cachePublic()
                .immutable());
```

Ví dụ giả định asset versioned nằm trong thư mục `assets`. Cần kiểm tra pattern mapping và thứ tự handler theo phiên bản Spring Framework của dự án; tránh để pattern tổng quát áp dụng nhầm policy. Một lựa chọn dễ quản lý là tách HTML và asset thành hai URL prefix/resource roots.

Không đặt cache một năm và immutable cho file tên cố định nếu nội dung có thể thay đổi tại URL đó.

## 7. Cấu hình cache bằng Spring Boot properties

Với static resources mặc định, Spring Boot cung cấp nhóm property `spring.web.resources.cache`.

Ví dụ:

```properties
spring.web.resources.cache.cachecontrol.max-age=5m
spring.web.resources.cache.cachecontrol.cache-public=true
```

Có thể dùng `spring.web.resources.cache.period` cho thời gian cache. Khi cần directive rõ như public/private/no-cache/no-store, nhóm `cachecontrol` diễn đạt policy cụ thể hơn.

Các property này áp dụng cho static resource handling mặc định. Nếu đã đăng ký custom handler và đặt `setCacheControl`, hãy kiểm tra policy của handler đó; không mặc định mọi property tự áp dụng giống nhau cho handler tùy chỉnh.

`spring.web.resources.add-mappings` và `spring.web.resources.static-locations` điều khiển việc bật mapping/vị trí resource, không phải cache policy. Đừng nhầm chúng với cấu hình Cache-Control.

## 8. Conditional GET, Last-Modified và ETag

Cache còn cho phép browser hỏi server tài nguyên đã thay đổi chưa.

- `Last-Modified`: thời điểm resource được sửa gần nhất.
- `If-Modified-Since`: client gửi thời điểm đã nhận; server có thể trả 304 nếu resource chưa thay đổi.
- `ETag`: validator đại diện một phiên bản representation.
- `If-None-Match`: client gửi ETag đã lưu; server có thể trả 304 nếu representation vẫn tương ứng.

Spring MVC static resource handling hỗ trợ last-modified/conditional request tùy resource và framework version. Không mặc định mọi cấu hình tự sinh ETag cho mọi file. Nếu cần ETag, xác minh response thực tế hoặc cấu hình validator phù hợp.

Ví dụ conditional request:

```http
GET /api-reference/index.html HTTP/1.1
If-Modified-Since: Tue, 17 Nov 2026 02:00:00 GMT
```

Nếu resource chưa thay đổi kể từ thời điểm đó và validator hợp lệ, server có thể trả:

```http
HTTP/1.1 304 Not Modified
Cache-Control: no-cache
Last-Modified: Tue, 17 Nov 2026 02:00:00 GMT
```

Response 304 không gửi lại body HTML; browser dùng bản đã cache. Ngày trong ví dụ chỉ minh họa định dạng, không phải giá trị cần hardcode.

### 8.1. Chọn max-age, no-cache hay no-store

- `max-age` cho phép browser dùng bản cache trong thời gian fresh mà không hỏi server.
- `no-cache` cho phép lưu nhưng yêu cầu revalidate trước khi dùng lại.
- `no-store` yêu cầu không lưu response.

Với HTML `current`, `no-cache` phù hợp khi muốn browser kiểm tra release mới nhưng vẫn tận dụng conditional request. Với asset versioned, max-age dài và immutable giảm request lặp lại.

## 9. Cache và tài liệu có xác thực

Nếu docs chỉ dành cho user đăng nhập hoặc role cụ thể:

- Dùng authorization để giới hạn người truy cập.
- Cân nhắc `private` để shared cache không lưu response.
- Dùng `no-store` khi response chứa dữ liệu nhạy cảm hoặc không được lưu.
- Không dùng `public` cho response phụ thuộc user/session.
- Kiểm tra CDN/reverse proxy có tuân thủ Cache-Control hay override header không.

Ví dụ cache policy cho docs nội bộ:

```java
registry.addResourceHandler("/internal-api-docs/**")
        .addResourceLocations("classpath:/static/internal-docs/")
        .setCacheControl(CacheControl.noStore());
```

Đây chỉ là cache policy; security filter chain vẫn phải yêu cầu authentication/authorization cho prefix này. Cache header không thay thế quyền truy cập.

## 10. Context path và reverse proxy

Nếu ứng dụng đặt context path `/service`, URL có thể là `/service/api-reference/index.html`. Nếu gateway expose ứng dụng dưới prefix `/platform`, public URL có thể là `/platform/service/api-reference/index.html`.

| Thành phần | Ví dụ |
| --- | --- |
| Classpath resource | `static/docs/index.html` |
| Resource handler pattern | `/api-reference/**` |
| Context path | `/service` |
| Public gateway prefix | `/platform` |
| Public URL | `/platform/service/api-reference/index.html` |

Dùng relative links trong HTML khi có thể. Nếu Asciidoctor sinh absolute URL, cấu hình base path đúng theo deployment. Kiểm tra redirect Location, asset URL và cache headers từ phía client bên ngoài gateway.

## 11. Kiểm thử URL và cache headers

Có thể dùng MockMvc để xác minh response. Ví dụ HTML có policy no-cache:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ApiDocsCacheHeadersTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void servesDocsWithExpectedCacheControl() throws Exception {
        mockMvc.perform(get("/api-reference/index.html"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.CACHE_CONTROL,
                        containsString("no-cache")
                ))
                .andExpect(content().contentTypeCompatibleWith(MediaType.TEXT_HTML));
    }
}
```

Nếu cấu hình policy khác, thay expectation theo giá trị thực tế. Với max-age, kiểm tra directive cần thiết thay vì so sánh nguyên chuỗi vì thứ tự directive có thể thay đổi.

Kiểm tra asset riêng:

```java
mockMvc.perform(get("/api-reference/assets/site.abc123.css"))
        .andExpect(status().isOk())
        .andExpect(header().string(
                HttpHeaders.CACHE_CONTROL,
                allOf(
                    containsString("max-age"),
                    containsString("immutable")
                )
        ))
        .andExpect(content().contentTypeCompatibleWith("text/css"));
```

Ví dụ giả định resource versioned thực sự tồn tại và handler đã áp dụng policy immutable đúng pattern.

### 11.1. Kiểm tra conditional request

Nếu server trả Last-Modified, lấy giá trị từ response đầu tiên rồi gửi `If-Modified-Since` trong request tiếp theo để xác minh 304 khi resource chưa đổi. Không hardcode timestamp phụ thuộc môi trường.

Smoke test sau khi chạy executable JAR nên xác minh:

1. HTML trả 200.
2. CSS/ảnh trả 200.
3. Cache-Control có directive dự kiến.
4. Conditional request trả 304 nếu validator được hỗ trợ.
5. Sau release, URL current trả nội dung mới và URL versioned cũ giữ nội dung cũ.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| URL docs 404 | Prefix handler không khớp hoặc file không ở classpath | Kiểm tra archive và resource mapping |
| `/docs/` không mở index | Không có welcome-page mapping cho thư mục con | Dùng `/docs/index.html` hoặc redirect có test |
| Browser thấy HTML cũ | max-age quá dài ở URL current | Dùng no-cache/max-age ngắn cho HTML current |
| CSS cũ sau release | URL asset cố định nhưng cache dài | Version/hash asset hoặc purge cache |
| no-cache bị hiểu là không lưu | Nhầm revalidation với no-store | Dùng no-store khi cần cấm lưu |
| Docs private bị shared cache giữ | Dùng public cho nội dung có authorization | Dùng private/no-store và kiểm tra CDN |
| ETag không xuất hiện | Giả định framework tự tạo ETag cho mọi resource | Xác minh response và cấu hình validator nếu cần |
| Asset versioned vẫn cache ngắn | Handler pattern không match hoặc policy bị handler khác áp dụng | Kiểm tra resource handler mapping |
| Gateway trả URL sai | Context path/proxy prefix chưa được tính | Kiểm tra forwarded headers và public URL |
| Test cache header thất thường | So sánh nguyên chuỗi hoặc hardcode timestamp | Assert directive cần thiết, lấy validator từ response |

## 13. Bài thực hành

Thiết lập URL và cache policy cho tài liệu User API:

1. Đóng gói docs dưới `classpath:/static/docs/`.
2. Đăng ký URL `/api-reference/**` bằng `ResourceHandlerRegistry`.
3. Đặt HTML entry point tại `/api-reference/index.html`.
4. Tách asset vào thư mục versioned như `assets/v2/` hoặc dùng tên file chứa hash.
5. Cấu hình HTML current dùng `no-cache` hoặc max-age ngắn.
6. Cấu hình asset versioned dùng max-age dài và immutable.
7. Nếu docs private, yêu cầu role phù hợp và không dùng cache-public.
8. Viết MockMvc test xác minh URL, Content-Type và Cache-Control.
9. Gửi conditional request dựa trên validator server thực sự trả về; kiểm tra 304 nếu được hỗ trợ.
10. Chạy executable JAR sau gateway/context path và xác minh public URL cùng asset URL.

**Tiêu chí hoàn thành:** chọn được URL stable/versioned; giải thích đúng max-age, public/private, no-cache/no-store và immutable; cấu hình cache cho HTML và assets; kiểm tra response headers và conditional request; không để shared cache lưu tài liệu riêng tư.

## 14. Câu hỏi tự kiểm tra

**1. Classpath static/docs/index.html có URL mặc định nào?**

Thông thường là `/docs/index.html`; phần `static` không xuất hiện trong URL.

**2. Vì sao HTML và CSS/JS có thể cần cache policy khác nhau?**

HTML current thường thay đổi theo release, còn asset versioned có thể bất biến theo URL và cache lâu hơn.

**3. no-cache khác no-store thế nào?**

no-cache cho phép lưu nhưng phải revalidate trước khi dùng lại; no-store yêu cầu không lưu response.

**4. public có phù hợp với docs yêu cầu đăng nhập không?**

Không nên. Response phụ thuộc quyền truy cập cần policy private/no-store thích hợp và security enforcement.

**5. Có nên đặt immutable cho URL /api-reference/index.html không?**

Không nếu URL luôn trỏ tới bản hiện hành. Immutable phù hợp URL versioned/hash có nội dung không đổi.

**6. dependsOn trong Gradle có đặt cache header không?**

Không. dependsOn thuộc build task graph; cache headers được cấu hình ở HTTP resource handling hoặc proxy/CDN.

**7. Làm sao xác minh ETag hoặc Last-Modified?**

Gọi resource endpoint, đọc response headers rồi gửi conditional request tương ứng. Không giả định ETag tự xuất hiện nếu chưa cấu hình hoặc xác minh.

## Tài liệu tham khảo

- [Spring Boot — Static Content](https://docs.spring.io/spring-boot/reference/web/servlet.html#web.servlet.spring-mvc.static-content): static locations và cấu hình static resources.
- [Spring Framework — Serving Static Resources](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html): resource handler, CacheControl và conditional requests.
- [Spring Framework — CacheControl API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/CacheControl.html): các directive và builder Cache-Control.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html): semantics của HTTP cache directives.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): conditional requests, validators và response semantics.

