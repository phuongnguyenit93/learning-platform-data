# Quản lý cấu hình môi trường và tài nguyên View

## 1. Vì sao cấu hình môi trường và tài nguyên View cần được quản lý riêng?

Ứng dụng Model–View–Controller thường chạy ở nhiều môi trường như máy lập trình, kiểm thử, staging và production. Cùng một chức năng có thể cần địa chỉ database khác nhau, URL dịch vụ đối tác khác nhau, mức log khác nhau hoặc chính sách cache khác nhau. Nếu những giá trị này được viết cứng trong Controller, Service hay template, mỗi lần triển khai sẽ dễ phải sửa mã nguồn và tạo ra sai lệch giữa các môi trường.

View cũng sử dụng nhiều tài nguyên: template HTML, CSS, JavaScript, hình ảnh, font, biểu tượng và thông điệp đa ngôn ngữ. Những tài nguyên này có vòng đời và cách phân phối khác nhau. Template thường được đóng gói cùng ứng dụng; tài nguyên tĩnh có thể được cache dài hạn hoặc phân phối qua CDN; nội dung do người dùng tải lên cần lưu trữ và kiểm soát truy cập riêng.

Quản lý tốt hai nhóm này giúp ứng dụng:

- Chuyển môi trường bằng cấu hình triển khai mà không sửa mã nguồn.
- Giữ bí mật như mật khẩu, token và khóa API khỏi repository, log và response.
- Kiểm tra cấu hình ngay khi khởi động để phát hiện thiếu hoặc sai giá trị.
- Tổ chức template và static resources theo quy ước dễ tìm, dễ kiểm thử.
- Cache tài nguyên tĩnh hiệu quả mà không làm người dùng nhận nội dung cũ.
- Phân biệt tài nguyên công khai với dữ liệu cá nhân hoặc tệp cần phân quyền.

Trong MVC, Controller không nên biết đường dẫn ổ đĩa hoặc URL CDN cụ thể. Controller trả tên View logic và dữ liệu trình bày; cơ chế cấu hình, View Resolver và Resource Handler chịu trách nhiệm tìm tài nguyên tương ứng.

## 2. Phân biệt cấu hình ứng dụng và tài nguyên View

Hai khái niệm có liên quan đến triển khai nhưng có mục đích khác nhau:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Application configuration | Điều khiển hành vi và kết nối của ứng dụng | Database URL, page size, API endpoint, timeout, feature flag |
| Secret | Giá trị xác thực hoặc dữ liệu bí mật | Database password, API key, signing key |
| View template | Mẫu cấu trúc để render response | `books/detail.html`, `errors/404.html` |
| Static resource | Tệp được trình duyệt tải riêng | CSS, JavaScript, ảnh, font |
| Message resource | Thông điệp theo ngôn ngữ hoặc locale | `messages_vi.properties`, `messages_en.properties` |
| User-generated content | Nội dung được tạo hoặc tải lên khi ứng dụng chạy | Ảnh bìa, tệp đính kèm, tài liệu riêng tư |

Không nên coi mọi tệp nằm trong thư mục `resources` là có cùng chính sách. Template được xử lý bởi template engine; static resource được gửi nguyên dạng cho client; message bundle được dùng để tra cứu chuỗi; tệp người dùng tạo ra thường phải nằm ở vùng lưu trữ riêng.

## 3. Cấu hình không nên viết cứng trong mã nguồn

Ví dụ không nên đặt trực tiếp thông tin môi trường trong Service:

~~~java
public class PartnerClient {
    private static final String BASE_URL =
            "https://partner-prod.example.internal";
    private static final String API_KEY = "secret-value";
}
~~~

Cách viết này làm mã nguồn gắn với production, khiến secret có thể bị commit vào Git và buộc phải biên dịch lại khi thay endpoint.

Thay vào đó, mã nguồn đọc cấu hình từ bên ngoài:

~~~yaml
app:
  partner:
    base-url: https://partner.example.com
    connect-timeout: 2s
    read-timeout: 5s
~~~

Đây là cấu hình mặc định không chứa bí mật. Môi trường triển khai có thể ghi đè URL hoặc timeout bằng environment variable, file cấu hình ngoài hoặc hệ thống quản lý cấu hình. API key được cấp từ secret store hoặc môi trường runtime riêng.

Nguyên tắc là mã nguồn chứa giá trị mặc định an toàn và quy tắc đọc cấu hình; môi trường triển khai cung cấp giá trị cụ thể. Không để template hoặc Controller tự đọc biến môi trường ở nhiều nơi.

## 4. Externalized Configuration trong Spring Boot

Spring Boot hỗ trợ externalized configuration: cùng một artifact có thể nhận cấu hình từ nhiều nguồn. Các nguồn thường dùng gồm:

- `application.yml` hoặc `application.properties` được đóng gói trong ứng dụng.
- File cấu hình bên ngoài thư mục chạy hoặc được chỉ định khi khởi động.
- Profile-specific configuration như `application-prod.yml`.
- Environment variables của container hoặc máy chủ.
- Java system properties và command-line arguments.
- Config tree, secret manager hoặc hệ thống cấu hình được tích hợp.

Giá trị ở nguồn có độ ưu tiên cao hơn có thể ghi đè giá trị ở nguồn thấp hơn. Thứ tự chính xác còn phụ thuộc loại nguồn và cách khởi chạy Spring Boot; khi điều tra một giá trị bất ngờ, hãy xem cấu hình thực tế và property source đang cung cấp nó thay vì đoán.

Ví dụ, `application.yml` đặt mặc định:

~~~yaml
app:
  catalog:
    page-size: 20
    cache-ttl: 60s
~~~

Môi trường production có thể đặt biến:

~~~text
APP_CATALOG_PAGESIZE=50
APP_CATALOG_CACHETTL=120s
~~~

Spring Boot relaxed binding ánh xạ tên biến môi trường sang property tương ứng. Quy tắc là thay dấu chấm bằng dấu gạch dưới, bỏ dấu gạch nối và chuyển thành chữ hoa; vì vậy `app.catalog.page-size` ánh xạ thành `APP_CATALOG_PAGESIZE`, còn `app.catalog.cache-ttl` thành `APP_CATALOG_CACHETTL`.

### File cấu hình bên ngoài

Ứng dụng có thể nhận file cấu hình bên ngoài khi khởi chạy, ví dụ:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:./config/
~~~

Đường dẫn cụ thể phụ thuộc cấu trúc triển khai. `additional-location` bổ sung vị trí tìm cấu hình; `spring.config.location` có thể thay thế các vị trí mặc định. Hãy kiểm tra tài liệu phiên bản Spring Boot đang dùng trước khi thay đổi vị trí cấu hình, vì lựa chọn này có thể khiến file cấu hình đóng gói không còn được nạp như mong đợi.

Không đặt file cấu hình ngoài ở thư mục static public hoặc trong thư mục được web server phục vụ trực tiếp.

## 5. Dùng Profiles cho từng môi trường

Spring Profile cho phép kích hoạt một nhóm cấu hình theo môi trường. Ví dụ:

~~~text
src/main/resources/
  application.yml
  application-dev.yml
  application-test.yml
  application-prod.yml
~~~

Cấu hình chung trong `application.yml`:

~~~yaml
spring:
  application:
    name: library-web
  thymeleaf:
    cache: true

app:
  catalog:
    page-size: 20
    cache-ttl: 60s
~~~

Cấu hình phát triển `application-dev.yml`:

~~~yaml
spring:
  thymeleaf:
    cache: false
  web:
    resources:
      cache:
        cachecontrol:
          max-age: 0

app:
  catalog:
    page-size: 10
~~~

Cấu hình production `application-prod.yml`:

~~~yaml
spring:
  thymeleaf:
    cache: true
  web:
    resources:
      cache:
        cachecontrol:
          max-age: 365d
          cache-public: true

app:
  catalog:
    page-size: 50
~~~

Kích hoạt profile qua biến môi trường hoặc tham số khởi chạy, ví dụ `SPRING_PROFILES_ACTIVE=prod`. Không nên mặc định kích hoạt production profile trong mã nguồn dùng chung.

Profile chỉ chọn cấu hình; nó không phải cơ chế bảo mật. Không dựa vào `prod` profile để quyết định người dùng có quyền truy cập endpoint hay không. Phân quyền phải được thực thi bằng security policy ở mọi môi trường.

### Profile-specific documents

Spring Boot cũng hỗ trợ nhiều YAML document trong một file, phân tách bằng `---` và điều kiện `spring.config.activate.on-profile`. Cách này hữu ích khi cấu hình liên quan cần được đặt cạnh nhau, nhưng các file riêng thường dễ đọc hơn khi mỗi môi trường có nhiều thiết lập.

Không đặt `spring.profiles.active` trong một document chỉ được kích hoạt bởi profile; giá trị kích hoạt profile cần đến từ nguồn cấu hình bên ngoài hoặc document không bị điều kiện hóa.

## 6. Bind cấu hình có kiểu bằng @ConfigurationProperties

Với một nhóm cấu hình có nhiều thuộc tính, `@ConfigurationProperties` thường dễ kiểm soát hơn việc gọi `@Value` rải rác. Nó gom các giá trị theo một prefix, hỗ trợ kiểu dữ liệu phù hợp và có thể xác thực khi khởi động.

~~~java
import java.time.Duration;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.catalog")
public record CatalogProperties(
        @Min(1) @Max(200) int pageSize,
        @NotNull Duration cacheTtl
) {}
~~~

Đăng ký properties bằng `@ConfigurationPropertiesScan` trên lớp ứng dụng hoặc `@EnableConfigurationProperties(CatalogProperties.class)` trong cấu hình. Ví dụ dùng record với constructor binding trong các phiên bản Spring Boot hiện đại; không cần tự tạo setter nếu dùng kiểu immutable. Để các annotation Bean Validation như `@Min`, `@Max` và `@NotNull` được thực thi, ứng dụng cần có validation provider tương ứng trên classpath, thường qua `spring-boot-starter-validation`.

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class LibraryApplication {
    public static void main(String[] args) {
        SpringApplication.run(LibraryApplication.class, args);
    }
}
~~~

Service có thể nhận cấu hình qua constructor:

~~~java
@Service
public class BookCatalogService {
    private final CatalogProperties properties;

    public BookCatalogService(CatalogProperties properties) {
        this.properties = properties;
    }

    public int pageSize() {
        return properties.pageSize();
    }
}
~~~

Việc bind và validate khi khởi động giúp ứng dụng thất bại sớm nếu `page-size` bằng 0 hoặc `cache-ttl` không hợp lệ. Đây là cách tốt hơn để phát hiện lỗi cấu hình khi triển khai thay vì để request đầu tiên mới gặp lỗi.

### Khi nào dùng @Value?

`@Value` phù hợp với một vài giá trị đơn giản:

~~~java
@Value("${app.brand-name:Thư viện}")
private String brandName;
~~~

Với nhóm cấu hình có quan hệ, kiểu dữ liệu, validation hoặc cần tái sử dụng, ưu tiên `@ConfigurationProperties`. Tránh gọi `Environment.getProperty()` ở nhiều lớp vì làm nguồn cấu hình và giá trị mặc định khó theo dõi.

## 7. Quản lý secret và dữ liệu nhạy cảm

Secret gồm mật khẩu database, API key, token, private key, khóa ký cookie hoặc khóa mã hóa. Các giá trị này cần được quản lý riêng với cấu hình thông thường.

Không:

- Commit secret vào Git, kể cả trong file profile production.
- Đưa secret vào Docker image, frontend JavaScript, HTML hoặc static resource.
- Ghi secret vào log, exception message hoặc metrics tag.
- Đưa secret vào command line nếu môi trường có thể ghi lại process arguments.
- Trả secret qua Actuator endpoint hoặc API cấu hình.

Nên:

- Dùng secret manager hoặc kho bí mật của nền tảng triển khai.
- Cấp secret vào process bằng cơ chế runtime được kiểm soát.
- Giới hạn quyền đọc secret theo service identity và môi trường.
- Luân chuyển khóa/token theo quy trình và có khả năng thu hồi.
- Dùng giá trị mặc định không chứa secret; ứng dụng production nên fail fast nếu secret bắt buộc bị thiếu.

### Ví dụ inject secret bằng environment variable

~~~yaml
app:
  partner:
    api-key: ${APP_PARTNER_API_KEY}
~~~

Placeholder `${APP_PARTNER_API_KEY}` tra cứu biến môi trường có đúng tên `APP_PARTNER_API_KEY`; đây là tên được tham chiếu tường minh trong placeholder. Nếu bind trực tiếp property `app.partner.api-key` từ environment variable theo relaxed binding, tên tương ứng là `APP_PARTNER_APIKEY`. Spring sẽ báo lỗi nếu placeholder bắt buộc không có giá trị và không có nguồn khác cung cấp. Không nên thêm giá trị giả như `changeme` cho production vì ứng dụng có thể khởi động với cấu hình sai mà không báo lỗi.

Trong môi trường hỗ trợ mounted secret files, Spring Boot có thể nạp config tree. Ví dụ cấu hình import:

~~~yaml
spring:
  config:
    import: optional:configtree:/run/secrets/
~~~

Nếu thư mục có file `app.partner.api-key`, nội dung file được đưa vào property `app.partner.api-key`. Bỏ `optional:` nếu secret bắt buộc và việc thiếu nó phải ngăn ứng dụng khởi động. Đường dẫn mount và quyền file do nền tảng triển khai quản lý.

Không đưa secret vào `BookDetailView`, Form DTO hoặc bất kỳ View Model nào. Một giá trị cấu hình server-side không trở thành an toàn chỉ vì template không hiển thị nó.

## 8. Cấu hình có thể thay đổi và thời điểm áp dụng

Đa số cấu hình Spring Boot được bind khi ApplicationContext khởi tạo. Thay đổi environment variable hoặc file cấu hình trên máy đang chạy không tự động làm mọi bean cập nhật giá trị.

Nếu cần đổi cấu hình, có thể triển khai theo một trong các cách:

- Thay cấu hình rồi restart/redeploy instance.
- Dùng nền tảng cấu hình động có cơ chế refresh được thiết kế và kiểm soát rõ.
- Đọc một giá trị động từ nguồn chuyên dụng tại thời điểm cần, nếu yêu cầu nghiệp vụ thực sự cần thay đổi tức thời.

Không giả định `@ConfigurationProperties` tự refresh sau khi file thay đổi. Cơ chế refresh động phụ thuộc thư viện và kiến trúc được dùng; cần xem xét tính nhất quán khi nhiều instance nhận cấu hình ở thời điểm khác nhau.

Với các giá trị nhạy cảm như key ký token, việc luân chuyển cần có chiến lược tương thích khóa cũ/mới và thời gian chuyển tiếp. Chỉ thay chuỗi trong cấu hình có thể làm session hoặc token đang hoạt động mất hiệu lực.

## 9. Cấu trúc tài nguyên View trong Spring MVC

Với Spring Boot và Thymeleaf, cấu trúc phổ biến:

~~~text
src/main/resources/
  templates/
    books/
      list.html
      detail.html
      form.html
    errors/
      404.html
      500.html
  static/
    css/
      app.css
    js/
      app.js
    images/
      logo.svg
    fonts/
      interface.woff2
  messages.properties
  messages_vi.properties
  messages_en.properties
~~~

`templates/` chứa file được template engine xử lý. `static/` chứa tài nguyên có thể được gửi trực tiếp đến trình duyệt. Message bundles chứa chuỗi theo locale. Không đặt mật khẩu, file cấu hình nội bộ hoặc dữ liệu người dùng trong `static/`.

### Tên View logic và template resolver

Controller trả tên View logic:

~~~java
@GetMapping("/books")
public String list(Model model) {
    model.addAttribute("books", bookService.list());
    return "books/list";
}
~~~

Với cấu hình Thymeleaf mặc định của Spring Boot, `books/list` thường được ánh xạ đến `classpath:/templates/books/list.html`. Prefix và suffix có thể được cấu hình bằng `spring.thymeleaf.prefix` và `spring.thymeleaf.suffix`.

Không trả trực tiếp đường dẫn file do client gửi lên:

~~~java
// Không dùng tên template từ request parameter.
return request.getParameter("view");
~~~

Tên View logic phải được ứng dụng chọn từ một tập tên cố định hoặc từ nhánh điều phối đã kiểm tra. Điều này ngăn truy cập template ngoài ý muốn và giữ cho Controller không phụ thuộc đường dẫn vật lý.

## 10. Template cache theo môi trường

Template engine thường cache template đã phân tích để giảm chi phí đọc và parse. Trong môi trường phát triển, tắt cache giúp thay đổi template dễ quan sát; trong production, bật cache để tránh parse lại mỗi request.

~~~yaml
# application-dev.yml
spring:
  thymeleaf:
    cache: false
~~~

~~~yaml
# application-prod.yml
spring:
  thymeleaf:
    cache: true
~~~

Đây là cấu hình dành cho Thymeleaf. Nếu dùng FreeMarker, Mustache hoặc một View technology khác, thuộc tính và cơ chế cache sẽ khác. Không nên áp dụng thuộc tính Thymeleaf cho mọi View Resolver.

Template được đóng gói trong executable JAR thường là tài nguyên chỉ đọc. Không thiết kế tính năng sửa template bằng cách ghi đè file trong classpath của ứng dụng đang chạy. Nếu cần tùy biến giao diện runtime, hãy thiết kế một kho template có version, quyền sửa, kiểm duyệt và cơ chế reload an toàn riêng.

## 11. Quản lý static resources

Static resources gồm CSS, JavaScript, hình ảnh và font. Spring Boot thường phục vụ tài nguyên từ các vị trí classpath như `/static`, `/public`, `/resources` hoặc `/META-INF/resources` theo cấu hình mặc định.

Trong template Thymeleaf, dùng URL được xử lý theo context path:

~~~html
<link rel="stylesheet" th:href="@{/css/app.css}" />
<script th:src="@{/js/app.js}" defer></script>
<img th:src="@{/images/logo.svg}" alt="Logo thư viện" />
~~~

Không ghép URL bằng cách nối chuỗi với context path trong nhiều template. URL expression giúp framework xử lý context path và các cơ chế resource URL được cấu hình.

### Thêm Resource Handler tùy chỉnh

Nếu cần phục vụ một thư mục classpath riêng, có thể đăng ký `ResourceHandler`:

~~~java
@Configuration
public class StaticResourceConfiguration implements WebMvcConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/assets/")
                .setCacheControl(CacheControl.maxAge(
                        365, TimeUnit.DAYS).cachePublic());
    }
}
~~~

Ví dụ cần import `CacheControl`, `TimeUnit`, `Configuration`, `ResourceHandlerRegistry` và `WebMvcConfigurer`. `classpath:/assets/` là vị trí tài nguyên được đóng gói cùng ứng dụng. Không dùng `file:` trỏ đến một đường dẫn tùy ý do request cung cấp.

Khi thêm handler, cần kiểm tra các đường dẫn mặc định vẫn được phục vụ đúng và handler không vô tình ánh xạ URL nhạy cảm. Không tạo resource handler cho thư mục chứa cấu hình, secret, log hoặc dữ liệu riêng tư.

## 12. Cache-Control, ETag và versioning

Trình duyệt và CDN có thể cache static resource để giảm số request và thời gian tải. Chính sách cache phải phù hợp với cách phát hành tài nguyên.

**Tên file ổn định** như `app.css` có thể bị giữ trong cache sau khi nội dung đã thay đổi. Nếu đặt `max-age` dài, người dùng có thể tiếp tục nhận bản cũ.

**Tên file có fingerprint/hash nội dung** như `app.8f3a1c.css` thay đổi khi nội dung thay đổi. Khi URL mới xuất hiện, trình duyệt tải bản mới; URL cũ có thể được cache dài hạn.

Ví dụ cấu hình resource chain theo content hash trong Spring Boot:

~~~yaml
spring:
  web:
    resources:
      chain:
        strategy:
          content:
            enabled: true
            paths: "/**"
      cache:
        cachecontrol:
          max-age: 365d
          cache-public: true
~~~

Resource chain và URL versioning cần được cấu hình, tích hợp đúng với template URL generation và cách triển khai. Một lựa chọn khác là dùng build tool tạo file có hash trong tên ngay khi build frontend. Không giả định chỉ bật cache-control là tự đổi URL khi nội dung thay đổi.

Với nội dung có hash trong URL, có thể dùng cache dài hạn và `immutable` nếu hệ thống hỗ trợ header phù hợp. Với tên file ổn định, dùng thời gian cache ngắn hơn hoặc revalidation qua ETag/Last-Modified.

### Không cache response cá nhân như static resource

Trang tài khoản, hóa đơn hoặc response chứa dữ liệu theo người dùng cần chính sách cache riêng, thường là `private` hoặc `no-store` tùy độ nhạy cảm. Không đặt `cache-public` chung cho mọi endpoint chỉ vì static asset cần cache dài hạn.

Static asset công khai và response HTML/JSON cá nhân phải có ranh giới URL, handler và header rõ ràng. CDN không được cache chéo dữ liệu giữa người dùng hoặc tenant.

## 13. Tách user-generated content khỏi static assets

Ảnh bìa do quản trị viên tải lên, tài liệu cá nhân hoặc file đính kèm không giống logo và CSS được phát hành cùng ứng dụng.

Không lưu file upload vào `src/main/resources/static` hoặc thư mục classpath của JAR. Những vị trí này thường chỉ đọc trong production, không phù hợp cho dữ liệu phát sinh khi ứng dụng chạy và có thể khiến nội dung được phục vụ công khai ngoài ý muốn.

Thay vào đó, lưu file trong object storage hoặc volume riêng, kèm metadata như owner, tenant, content type đã xác minh, kích thước, checksum và trạng thái kiểm duyệt. Khi người dùng tải file, Controller/Service kiểm tra quyền rồi trả stream hoặc URL có thời hạn theo chính sách.

Không tạo URL công khai cho file riêng tư chỉ bằng cách đoán tên file khó đoán. ID khó đoán không thay thế authorization. Cần kiểm tra quyền đọc ở mỗi request hoặc dùng signed URL có thời hạn ngắn và phạm vi đối tượng rõ ràng.

Với file được phục vụ trực tiếp, kiểm tra loại nội dung thực tế, giới hạn kích thước, tạo tên lưu trữ do server kiểm soát và tránh thực thi nội dung tải lên. Không tin phần mở rộng hoặc `Content-Type` do client tự khai báo.

## 14. Đa ngôn ngữ và Message Resources

View thường chứa nhãn, thông báo validation và nội dung điều hướng. Không nên viết cứng mọi chuỗi trong template nếu ứng dụng cần nhiều ngôn ngữ.

Spring dùng `MessageSource` để tra cứu message theo code và locale. Với Spring Boot, file mặc định có thể là `messages.properties`, kèm các file như `messages_vi.properties` và `messages_en.properties`.

Ví dụ `messages_vi.properties`:

~~~properties
book.title=Tiêu đề sách
book.create.success=Đã tạo sách thành công.
validation.title.required=Tiêu đề không được để trống.
~~~

Ví dụ `messages_en.properties`:

~~~properties
book.title=Book title
book.create.success=Book created successfully.
validation.title.required=Title is required.
~~~

Trong Thymeleaf:

~~~html
<label for="title" th:text="#{book.title}">Tiêu đề sách</label>
<p th:text="#{book.create.success}">Đã tạo sách thành công.</p>
~~~

Locale có thể được xác định từ `Accept-Language`, cookie, session hoặc tùy chọn người dùng theo chính sách ứng dụng. Với ứng dụng web, cần cấu hình `LocaleResolver` và nếu cho phép đổi ngôn ngữ qua URL hoặc cookie thì xác minh giá trị locale thuộc danh sách hỗ trợ.

Không ghép thông điệp bằng cách nối chuỗi tùy tiện nếu có tham số. Dùng message format có placeholder để giữ ngữ pháp phù hợp từng ngôn ngữ. Thông báo validation cũng nên dùng message code để có thể dịch.

## 15. Cấu hình View theo tenant hoặc thương hiệu

Một số ứng dụng cần giao diện khác nhau theo tenant, thương hiệu hoặc gói dịch vụ. Có thể biểu diễn các khác biệt an toàn bằng View Model hoặc theme configuration, chẳng hạn logo URL, tên hiển thị và màu thương hiệu.

Không dùng dữ liệu tenant từ request để ghép đường dẫn template tùy ý. Nếu có nhiều theme template, ánh xạ theme đã xác thực vào danh sách template cố định do ứng dụng quản lý. Quyền chọn theme và quyền sửa nội dung theme cần được kiểm tra ở server.

Với khác biệt chỉ về màu sắc hoặc logo, CSS variables và metadata trong View Model thường đủ; không cần nhân bản toàn bộ template. Nếu cần template khác nhau theo tenant, cần quản lý version, fallback và kiểm thử để một tenant không thể truy cập template của tenant khác.

## 16. Kiểm tra cấu hình và tài nguyên khi triển khai

Cấu hình sai có thể khiến ứng dụng khởi động nhưng chỉ thất bại khi người dùng truy cập một chức năng. Nên xác minh các thuộc tính bắt buộc ở startup bằng type binding và validation.

Một số kiểm tra vận hành hữu ích:

- Profile đang hoạt động đúng với môi trường triển khai.
- Database URL, endpoint đối tác và timeout trỏ đúng môi trường.
- Secret bắt buộc có mặt và không dùng giá trị mẫu.
- Template cần thiết được đóng gói trong artifact.
- Static assets được phục vụ dưới đúng context path.
- Resource URL versioning hoạt động sau mỗi lần build.
- Cache-Control phù hợp với static asset và response cá nhân.
- Message bundle có đủ key cho các locale được hỗ trợ.
- CDN hoặc reverse proxy không cache nhầm response có dữ liệu người dùng.
- Thư mục lưu file upload không nằm trong vùng public ngoài ý muốn.

Actuator có thể cung cấp endpoint quan sát cấu hình như `env` hoặc `configprops` tùy cách cấu hình và phiên bản. Các endpoint này có thể tiết lộ tên property, cấu trúc hệ thống hoặc giá trị nhạy cảm nếu cấu hình không đúng. Chỉ mở cho quản trị nội bộ, giới hạn quyền truy cập, che giá trị nhạy cảm và không public chúng trên Internet.

Không cần expose toàn bộ environment để debug production. Hãy ưu tiên log tên profile, phiên bản ứng dụng và các trạng thái cấu hình không nhạy cảm; không log giá trị secret.

## 17. Kiểm thử cấu hình và tài nguyên View

Kiểm thử nên xác minh cả việc bind cấu hình lẫn việc framework tìm đúng tài nguyên:

| Loại kiểm thử | Nội dung |
|---|---|
| Configuration binding test | Giá trị mặc định, environment override, kiểu Duration/URI và validation |
| Profile test | Cấu hình dev/test/prod được kích hoạt đúng |
| Context startup test | Thiếu secret hoặc property bắt buộc làm ứng dụng fail fast |
| Controller/View test | Controller trả đúng tên View và Model attribute |
| Template integration test | Template tồn tại, message key và biểu thức được resolve |
| Static resource test | URL asset trả đúng content type, body và cache header |
| Cache/version test | URL thay đổi khi nội dung có hash thay đổi; cache policy đúng |
| Security test | File riêng tư không thể tải bởi người dùng không có quyền |

Ví dụ kiểm tra binding với Spring Boot có thể dùng `ApplicationContextRunner` hoặc test context nhỏ, truyền property trực tiếp để xác minh giá trị và lỗi validation. Với test theo profile, đặt profile rõ trong test thay vì dựa vào biến môi trường của máy phát triển.

Với `MockMvc`, có thể kiểm tra Controller trả View logic đúng và Model có dữ liệu mong đợi; test này chưa chắc render template thật. Để phát hiện thiếu file hoặc lỗi cú pháp template, cần integration test có template engine thực sự được cấu hình hoặc test chạy ứng dụng trong context phù hợp.

Static resource có thể được kiểm tra qua request GET bằng MockMvc hoặc integration test HTTP, xác minh `Content-Type`, `Cache-Control`, ETag và body. Với CDN, cần kiểm tra cấu hình ở tầng CDN/reverse proxy vì MockMvc không mô phỏng cache bên ngoài.

## 18. Những sai lầm thường gặp

- **Hardcode URL hoặc secret trong Java:** làm ứng dụng gắn với một môi trường và tăng nguy cơ lộ bí mật.
- **Dùng profile như cơ chế phân quyền:** profile chỉ chọn cấu hình, không bảo vệ endpoint.
- **Đặt secret trong application-prod.yml đã commit:** file profile không phải secret store.
- **Đọc environment variable rải rác trong Controller:** làm cấu hình khó kiểm soát và khó test.
- **Không validate cấu hình khi khởi động:** lỗi chỉ xuất hiện khi request đi vào nhánh hiếm.
- **Ghi template vào classpath lúc runtime:** executable JAR thường không phải vùng lưu trữ ghi được.
- **Phục vụ file upload từ static public:** có thể làm lộ tài liệu hoặc nội dung chưa kiểm duyệt.
- **Lấy tên template từ request:** có nguy cơ truy cập template ngoài dự kiến.
- **Cache dài cho URL asset ổn định:** người dùng có thể nhận CSS/JavaScript cũ.
- **Cache public cho response cá nhân:** có thể làm lộ dữ liệu giữa người dùng hoặc tenant.
- **Bật cache template ở môi trường phát triển mà không có quy trình reload:** thay đổi template khó được phản ánh.
- **Mở Actuator env/configprops công khai:** có thể lộ thông tin vận hành hoặc cấu hình.

## 19. Kết luận

Quản lý cấu hình môi trường giúp cùng một ứng dụng chạy ở dev, test, staging và production mà không cần sửa mã nguồn. Spring Boot cung cấp externalized configuration, profiles, environment variables, config tree và `@ConfigurationProperties` để bind, validate và quản lý cấu hình theo nhóm. Secret cần được cấp qua nguồn bảo mật và không xuất hiện trong repository, View hoặc log.

Tài nguyên View cần được phân loại theo cách sử dụng: template được View Resolver tìm theo tên logic; static resources được Resource Handler phục vụ; message bundles cung cấp nội dung theo locale; user-generated content cần lưu trữ và authorization riêng. Kết hợp cache, versioning, kiểm thử và chính sách truy cập phù hợp giúp giao diện được phân phối hiệu quả mà vẫn bảo vệ dữ liệu.

Khi triển khai MVC, hãy xác định nguồn và độ ưu tiên cấu hình, kiểm tra giá trị bắt buộc ngay lúc khởi động, tổ chức tài nguyên View theo đúng vai trò và áp dụng cache theo tính chất của từng response. Những ranh giới rõ ràng này giúp ứng dụng dễ chuyển môi trường, dễ vận hành và ít gặp lỗi do cấu hình hoặc tài nguyên.
