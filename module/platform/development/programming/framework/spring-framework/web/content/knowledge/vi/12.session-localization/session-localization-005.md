# LocaleResolver, LocaleContextResolver và lựa chọn ngôn ngữ trong Spring MVC

## 1. Bài toán: cùng một trang, nhiều ngôn ngữ

Một người truy cập website với HTTP header:

```http
GET /welcome HTTP/1.1
Accept-Language: vi-VN,vi;q=0.9,en;q=0.7
```

Họ mong thấy lời chào bằng tiếng Việt. Người khác gửi `Accept-Language: en-US,en;q=0.8` thì muốn thấy tiếng Anh. Sau đó người dùng có thể chọn ngôn ngữ thủ công, và lựa chọn đó nên được nhớ trong cookie hoặc session. Từ nhu cầu này có ba câu hỏi khác nhau:

1. **Ngôn ngữ (locale) hiện tại được chọn thế nào?** Spring MVC dùng một `LocaleResolver`.
2. **Nếu ngoài ngôn ngữ còn có múi giờ thì sao?** `LocaleContextResolver` mở rộng mô hình để trả về `LocaleContext`, có thể kèm `TimeZone`.
3. **Chọn locale rồi làm sao hiển thị văn bản được dịch?** `MessageSource`, resource bundles và template engine sử dụng locale đã chọn để tìm thông điệp. Resolver tự nó không dịch text.

Sau bài này, bạn sẽ biết các chiến lược `AcceptHeaderLocaleResolver`, `CookieLocaleResolver`, `SessionLocaleResolver` và `FixedLocaleResolver`; cấu hình `LocaleChangeInterceptor`; phân biệt language/region với time zone; xử lý fallback và supported languages; áp dụng `MessageSource` cho controller và Thymeleaf; tự kiểm thử bằng Spring Boot 3, Java 17 và MockMvc.

**Phạm vi:** Spring MVC **Servlet stack**, Spring Framework 6.x (ví dụ 6.2) và Spring Boot 3.x. Trong Spring WebFlux cũng có giao diện cùng tên `LocaleContextResolver` nhưng ở package `org.springframework.web.server.i18n` và dùng `ServerWebExchange`; **không được nhập nhầm** với Servlet MVC package `org.springframework.web.servlet`.

## 2. Locale là gì? Không nhầm với ngôn ngữ đơn thuần

`java.util.Locale` diễn tả ngôn ngữ và các thông tin văn hóa/địa phương như region, script, variant tùy trường hợp:

| Language tag | Ý nghĩa điển hình | `Locale.forLanguageTag(...)` |
| --- | --- | --- |
| `vi` | Tiếng Việt, chưa chỉ định quốc gia | `Locale.forLanguageTag("vi")` |
| `vi-VN` | Tiếng Việt ở Việt Nam | `Locale.forLanguageTag("vi-VN")` |
| `en` | Tiếng Anh nói chung | `Locale.forLanguageTag("en")` |
| `en-US` | Tiếng Anh ở Mỹ | `Locale.forLanguageTag("en-US")` |
| `en-GB` | Tiếng Anh ở Anh | `Locale.forLanguageTag("en-GB")` |
| `ja-JP` | Tiếng Nhật ở Nhật | `Locale.forLanguageTag("ja-JP")` |
| `zh-Hant-TW` | Tiếng Hoa chữ phồn thể, vùng Đài Loan | Locale gồm language/script/region |

Locale chi phối cách chọn **message**, format số, ngày, tiền tệ; nó **không nhất thiết quyết định múi giờ**. Cùng `en-US`, người dùng có thể đang ở New York, Seattle hoặc Hà Nội. `TimeZone` đại diện một thuộc tính độc lập như `Asia/Ho_Chi_Minh` hay `Europe/London`, đặc biệt quan trọng khi hiển thị `Instant` thành giờ địa phương.

Để parse BCP 47 language tag chuẩn, thường dùng:

```java
Locale vn = Locale.forLanguageTag("vi-VN");
Locale us = Locale.forLanguageTag("en-US");
System.out.println(vn.toLanguageTag());
System.out.println(us.getLanguage());
```

Đoạn minh họa có `import java.util.Locale;`, stdout tương ứng:

```text
vi-VN
en
```

Đây là Java logic minh họa; khi cần chạy độc lập, đặt vào một class có `main`. Trong URL parameter và cookie, dùng language tags nhất quán, ví dụ `vi`, `en` hoặc `vi-VN`, thay vì tùy tiện ghép string theo dấu gạch dưới.

### 2.1. Accept-Language không phải lựa chọn bắt buộc

HTTP `Accept-Language` thể hiện thứ tự **ưu tiên** của user agent; `q` từ 0 đến 1 thể hiện trọng số. Server có thể giới hạn các ngôn ngữ được hỗ trợ và chọn fallback phù hợp; không phải client đòi `fr-CA` thì ứng dụng bắt buộc có bản dịch `fr-CA`. Một số request từ API client không gửi header này. Lựa chọn thủ công trong tài khoản/cookie/session có thể được ưu tiên hơn header nếu đó là chính sách của ứng dụng.

Để API trung thực, hãy phân biệt:

- **Requested locale:** mong muốn được client trình bày.
- **Resolved locale:** kết quả mà chiến lược Spring MVC chọn cho request.
- **Message bundle thực sự dùng:** các bundle như `messages_vi.properties`; một key có thể fallback sang bundle mặc định dù resolved locale là `vi-VN`.
- **Time zone của người dùng:** thuộc tính độc lập, không suy ra từ ngôn ngữ.

## 3. Vai trò của LocaleResolver trong DispatcherServlet

Giao diện Servlet MVC:

```java
package org.springframework.web.servlet;

public interface LocaleResolver {
    Locale resolveLocale(HttpServletRequest request);

    void setLocale(HttpServletRequest request,
                   HttpServletResponse response,
                   Locale locale);
}
```

*Đây là bản trích chữ ký nhằm giải thích ý nghĩa, không phải source đầy đủ (các annotation nullability/docs được lược bỏ).*

`resolveLocale(request)` trả locale hiện tại theo một chiến lược: header, cookie, session hoặc fixed value. `setLocale(...)` yêu cầu đổi locale, nhưng **không phải implementation nào cũng hỗ trợ** thao tác này.

`DispatcherServlet` tìm bean có tên chính xác **`localeResolver`** trong context của nó. Nếu không có, mặc định Framework dùng `AcceptHeaderLocaleResolver`. Cách chọn này có thể được Spring Boot tự cấu hình hoặc bị override bằng bean custom.

Luồng đơn giản:

```text
HTTP request
    │
    ▼
DispatcherServlet
    │
    ├── Chọn HandlerMapping và controller
    │
    ├── LocaleResolver.resolveLocale(request)
    │       ├── Accept-Language
    │       ├── cookie
    │       ├── HttpSession
    │       └── fixed/fallback
    │
    ├── LocaleContextHolder / request context
    │       └── locale hiện tại của request
    │
    ├── Controller, Validator, Formatter, Template View
    │       └── MessageSource.getMessage(code, args, locale)
    │
    ▼
HTML/JSON hoặc thông báo theo ngôn ngữ đã chọn
```

**Không lưu locale người dùng vào một field mutable trên singleton controller.** Controller/service bean có thể phục vụ nhiều requests song song. Lấy locale theo request hoặc context hiện hành, hoặc truyền `Locale` một cách tường minh trong method.

### 3.1. Lấy locale trong code ứng dụng

Các lựa chọn:

```java
@GetMapping("/locale")
@ResponseBody
String locale(Locale locale) {
    return locale.toLanguageTag();
}
```

`Locale` method argument được Spring MVC resolve từ request. Các API liên quan:

- `LocaleContextHolder.getLocale()`: lấy locale gắn với context hiện tại, thường là thread xử lý Servlet request.
- `RequestContextUtils.getLocale(request)`: lấy locale từ request theo resolver MVC đã đăng ký.
- `RequestContextUtils.getTimeZone(request)`: lấy time zone nếu resolver hỗ trợ context thời gian; có thể trả null.

`LocaleContextHolder` dựa trên thread context, nên với `@Async`, executor, tác vụ nền hoặc thread tự tạo, **không mặc định** locale từ HTTP request được truyền qua. Khi dùng xử lý bất đồng bộ, hãy truyền locale rõ ràng hoặc thiết kế context propagation phù hợp; không giữ lại `HttpServletRequest` để dùng sau khi request đã kết thúc.

## 4. LocaleContextResolver khác LocaleResolver thế nào?

Trong **Servlet MVC**, `org.springframework.web.servlet.LocaleContextResolver` là interface **extends `LocaleResolver`** và bổ sung khả năng làm việc với `LocaleContext`:

```java
package org.springframework.web.servlet;

public interface LocaleContextResolver extends LocaleResolver {
    LocaleContext resolveLocaleContext(HttpServletRequest request);

    void setLocaleContext(HttpServletRequest request,
                          HttpServletResponse response,
                          LocaleContext localeContext);
}
```

*Chữ ký đã giản lược annotation và một số default methods để giải thích; `LocaleContext` thuộc `org.springframework.context.i18n`.*

`LocaleContext` có `getLocale()`. Khi thực thể context còn implements `TimeZoneAwareLocaleContext`, nó có thể cung cấp `getTimeZone()`.

Sơ đồ quan hệ:

```text
LocaleResolver
 ├── resolveLocale(request): Locale
 └── setLocale(request, response, locale)
          ▲
          │ extends
LocaleContextResolver
 ├── resolveLocaleContext(request): LocaleContext
 └── setLocaleContext(request, response, context)
       │
       └── LocaleContext
            ├── Locale getLocale()
            └── nếu TimeZoneAwareLocaleContext:
                 TimeZone getTimeZone()
```

Các class `CookieLocaleResolver`, `SessionLocaleResolver` và `FixedLocaleResolver` trong Spring MVC 6.x triển khai giao diện mở rộng này thông qua `AbstractLocaleContextResolver`. `AcceptHeaderLocaleResolver` triển khai `LocaleResolver` cơ bản: nó đọc ngôn ngữ từ header và không tự lưu timezone/selection của người dùng.

### 4.1. Khi nào cần time zone?

Ví dụ email booking lúc `2026-12-24T09:00:00Z`:

- Với time zone `Asia/Ho_Chi_Minh`, thời điểm tương ứng là 16:00 cùng ngày.
- Với `Europe/London` vào tháng 12, thời điểm tương ứng là 09:00 (giờ chuẩn GMT).

Locale chỉ định ngôn ngữ hiển thị như `vi` hoặc `en`; để hiển thị thời gian tuyệt đối, phải biết time zone. Khi chuyển `Instant`, ưu tiên `java.time.ZoneId`/`ZonedDateTime`. `TimeZone` từ LocaleContext có thể đổi sang `ZoneId` bằng `timeZone.toZoneId()`.

Ví dụ đọc time zone từ request:

```java
TimeZone timeZone = RequestContextUtils.getTimeZone(request);
ZoneId zone = timeZone != null
        ? timeZone.toZoneId()
        : ZoneId.of("UTC");

String localTime = instant.atZone(zone).toString();
```

*Đoạn minh họa cần `HttpServletRequest request`, `Instant instant` và import tương ứng. Fallback UTC ở đây là chính sách mẫu; không khẳng định mọi hệ thống nên dùng UTC cho giờ hiển thị.*

**Cần phân biệt:** `LocaleChangeInterceptor` đổi *locale*, không phải một giao diện đầy đủ để chọn *time zone*. Muốn đổi cả hai, ứng dụng có thể dùng `LocaleContextResolver#setLocaleContext(...)` với `SimpleTimeZoneAwareLocaleContext` nếu resolver cho phép, hoặc có endpoint/policy riêng.

## 5. Bốn chiến lược LocaleResolver thường gặp

| Resolver | Nguồn locale | Đổi được bằng `setLocale`? | Thời gian lưu | Có context múi giờ? |
| --- | --- | --- | --- | --- |
| `AcceptHeaderLocaleResolver` | `Accept-Language` trong HTTP request | **Không**; header do client quyết định | Theo từng request | Không triển khai LocaleContextResolver |
| `CookieLocaleResolver` | Cookie lưu lựa chọn, fallback nếu không có | **Có** | Theo cookie; cấu hình max age | Có |
| `SessionLocaleResolver` | `HttpSession` attribute, fallback nếu chưa chọn | **Có** | Trong phiên người dùng | Có |
| `FixedLocaleResolver` | Locale cố định do server cấu hình | **Không** đổi động | Cố định với mọi request | Có thể có default timezone |

Tất cả tồn tại trong package `org.springframework.web.servlet.i18n`. Việc chọn resolver phù hợp phụ thuộc mục tiêu: API nhận ngôn ngữ theo HTTP header, website cho khách chọn ngôn ngữ và lưu cookie, website đã có session, hoặc ứng dụng chỉ phục vụ một ngôn ngữ.

### 5.1. AcceptHeaderLocaleResolver

Đây là mặc định quen thuộc trong Spring MVC khi không đăng ký resolver khác. Nó dựa vào `ServletRequest.getLocale()` và/hoặc danh sách locale được hỗ trợ.

```java
@Bean
LocaleResolver localeResolver() {
    AcceptHeaderLocaleResolver resolver =
            new AcceptHeaderLocaleResolver();
    resolver.setSupportedLocales(List.of(
            Locale.forLanguageTag("vi"),
            Locale.forLanguageTag("en")
    ));
    resolver.setDefaultLocale(Locale.forLanguageTag("vi"));
    return resolver;
}
```

*Đây là cấu hình thay thế riêng, không dùng đồng thời với cookie resolver trong project mục 8.*

Với configured `supportedLocales`, Spring tìm locale phù hợp trong các ưu tiên của `Accept-Language`. Điểm dễ bỏ sót: việc so khớp có **ngôn ngữ và quốc gia**; nếu chỉ khai báo `en-US`, client gửi `en-GB` không tự động khớp. Muốn fallback theo ngôn ngữ, nên khai báo thêm `en` trong danh sách được hỗ trợ. Khi không khớp, dùng `defaultLocale` nếu có; nếu không thì fallback theo locale request.

**Quan trọng:** `AcceptHeaderLocaleResolver#setLocale(...)` không được hỗ trợ và có thể ném `UnsupportedOperationException`. Không ghép nó một cách mù quáng với `LocaleChangeInterceptor` nếu interceptor sẽ gọi `setLocale(...)` khi thấy query parameter.

### 5.2. CookieLocaleResolver

Cookie thích hợp cho website cần ghi nhớ lựa chọn ngôn ngữ qua các request mà không bắt buộc có server session:

```java
@Bean
LocaleResolver localeResolver() {
    CookieLocaleResolver resolver =
            new CookieLocaleResolver("SITE_LANG");
    resolver.setDefaultLocale(Locale.forLanguageTag("vi"));
    resolver.setCookieMaxAge(Duration.ofDays(30));
    resolver.setCookiePath("/");
    resolver.setCookieSameSite("Lax");
    resolver.setCookieHttpOnly(true);
    return resolver;
}
```

*Đoạn mã minh họa nằm trong `@Configuration`, cần import `LocaleResolver`, `CookieLocaleResolver`, `Duration` và `Locale`. Ứng dụng chạy đầy đủ ở mục 8.*

Khi người dùng chọn `lang=en`, một interceptor/controller có thể gọi `setLocale(...)` và gửi header `Set-Cookie` để lưu locale đã chọn. Request sau gửi lại cookie; resolver đọc giá trị đó. Cấu hình `maxAge` xác định thời hạn lưu; nếu muốn cookie chỉ sống trong phiên browser, chọn cấu hình phù hợp thay vì cố ép một thời hạn.

Cookie mang lựa chọn người dùng, không phải bằng chứng xác thực hay phân quyền. Không dùng cookie locale để tin cậy các trường bảo mật. Với HTTPS production, xét `Secure`, `SameSite`, `HttpOnly`, cookie path/domain, thời hạn lưu và chính sách privacy. Phản hồi có thể cần `Vary: Cookie` hoặc chính sách cache riêng khi HTML khác theo locale cookie.

Một lựa chọn cookie sau này có thể **ưu tiên hơn Accept-Language**. Nếu đã cố định `defaultLocale` trên resolver, locale fallback có thể dùng giá trị này thay vì header. Nên công bố thứ tự ưu tiên rõ trong sản phẩm.

### 5.3. SessionLocaleResolver

`SessionLocaleResolver` lưu locale/timezone trong `HttpSession`. Một cấu hình minh họa:

```java
@Bean
LocaleResolver localeResolver() {
    SessionLocaleResolver resolver = new SessionLocaleResolver();
    resolver.setDefaultLocale(Locale.forLanguageTag("vi"));
    return resolver;
}
```

Phù hợp với ứng dụng server-side đã có session và muốn giữ lựa chọn tạm trong thời gian session sống. Lựa chọn thường mất khi session hết hạn hoặc bị xóa. Nếu hệ thống không muốn tạo session, cân nhắc cookie hoặc AcceptHeader. Không đồng nhất session locale với profile language bền vững của tài khoản: nếu user đã đăng nhập, có thể cần đồng bộ lựa chọn lên database và load lại cho phiên sau.

### 5.4. FixedLocaleResolver

`FixedLocaleResolver` luôn trả một locale mặc định, có thể có default timezone:

```java
@Bean
LocaleResolver localeResolver() {
    return new FixedLocaleResolver(
            Locale.forLanguageTag("vi"),
            TimeZone.getTimeZone("Asia/Ho_Chi_Minh")
    );
}
```

*Đoạn minh họa đòi import `FixedLocaleResolver`, `Locale` và `TimeZone`; không chạy đồng thời với các bean resolver khác.*

Dùng khi ứng dụng có ngôn ngữ xác định, hoặc muốn behavior ổn định trong một môi trường. Không sử dụng `LocaleChangeInterceptor` để đổi động với fixed resolver vì `setLocale` không được hỗ trợ.

## 6. LocaleChangeInterceptor: cho người dùng chọn ngôn ngữ

`org.springframework.web.servlet.i18n.LocaleChangeInterceptor` là một `HandlerInterceptor`. Nó kiểm tra query parameter theo tên cấu hình (mặc định `locale`), parse thành locale rồi gọi `LocaleResolver#setLocale(request,response,locale)`.

Ví dụ URL:

```text
GET /welcome?lang=en
GET /welcome?lang=vi
```

Cấu hình:

```java
@Configuration
class WebLocaleConfig implements WebMvcConfigurer {

    @Bean
    LocaleResolver localeResolver() {
        CookieLocaleResolver resolver =
                new CookieLocaleResolver("SITE_LANG");
        resolver.setDefaultLocale(Locale.forLanguageTag("vi"));
        return resolver;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        LocaleChangeInterceptor interceptor =
                new LocaleChangeInterceptor();
        interceptor.setParamName("lang");
        interceptor.setHttpMethods("GET");
        registry.addInterceptor(interceptor);
    }
}
```

*Đoạn cấu hình minh họa; project hoàn chỉnh bên dưới có imports và cookie options.*

### 6.1. Trình tự trong request đổi ngôn ngữ

```text
GET /welcome?lang=en
       │
       ▼
HandlerMapping chọn controller + interceptor chain
       │
       ▼
LocaleChangeInterceptor.preHandle(...)
       ├── phát hiện param lang=en
       ├── parse Locale("en")
       └── resolver.setLocale(request, response, Locale.ENGLISH)
                  ├── CookieLocaleResolver ghi cookie
                  └── resolver lưu locale cho request hiện tại
       │
       ▼
Controller hoặc View dùng locale đã được chọn
       │
       ▼
MessageSource lấy message từ messages_en.properties
```

Trong cùng request, resolver hỗ trợ cập nhật locale để handler/view đọc được lựa chọn mới. Browser giữ cookie và gửi lại sau đó.

### 6.2. Tránh ghép interceptor với resolver không thay đổi được

Bảng:

| Resolver | `?lang=en` với LocaleChangeInterceptor |
| --- | --- |
| `AcceptHeaderLocaleResolver` | Không phù hợp; `setLocale` có thể ném `UnsupportedOperationException` |
| `FixedLocaleResolver` | Không phù hợp; không cho thay locale động |
| `CookieLocaleResolver` | Phù hợp; viết cookie |
| `SessionLocaleResolver` | Phù hợp; lưu vào session |

`setParamName("lang")` thay đổi tên query parameter. Có thể `setHttpMethods("GET")` để giới hạn kiểu request được phép đổi locale; `setIgnoreInvalidLocale(true)` cho phép bỏ qua chuỗi locale parse sai, nhưng **không phải whitelist ngôn ngữ hỗ trợ**.

**Lưu ý bảo mật/UX:** đừng cho vô hạn language tag từ client rồi dùng nó trong file path/SQL hoặc nghiệp vụ. Parse locale không chứng minh ngôn ngữ đó có message bundle. Có thể whitelist các lựa chọn `vi`, `en` tại UI và kiểm tra đầu vào phía server; khi ngôn ngữ không được hỗ trợ, từ chối hoặc fallback có chủ đích. Nếu đổi locale qua GET có tác dụng lưu cookie, hãy cân nhắc cache/crawlers/CSRF/privacy và quyết định hợp đồng phù hợp, không dùng nó cho nghiệp vụ có tác động quan trọng.

## 7. MessageSource và template engine: chọn ngôn ngữ chưa phải dịch

`LocaleResolver` chỉ chọn locale. Câu `"Welcome"`, `"Xin chào"` thuộc **message bundles** được quản lý bởi `MessageSource`, ví dụ:

```properties
# messages.properties - bundle mặc định
greeting=Welcome!
title=Locale demonstration
```

```properties
# messages_vi.properties
greeting=Xin chào!
title=Ví dụ ngôn ngữ
```

```properties
# messages_en.properties
greeting=Hello!
title=Language example
```

Controller có thể gọi:

```java
@GetMapping("/api/message")
Map<String, String> message(HttpServletRequest request) {
    Locale locale = RequestContextUtils.getLocale(request);
    String text = messageSource.getMessage("greeting", null, locale);
    return Map.of(
            "language", locale.getLanguage(),
            "message", text);
}
```

*Đoạn này minh họa một handler trong controller có field `MessageSource messageSource` được inject; project đầy đủ nằm ở mục 8.*

Với Thymeleaf, dùng expression `#{greeting}`:

```html
<h1 th:text="#{greeting}">Default greeting</h1>
```

Đó là expression tra MessageSource theo locale của request. Khác với `${someModelValue}` dùng để tra model variable; dấu `#` và dấu `$` có ý nghĩa khác nhau.

### 7.1. Spring Boot MessageSource auto-configuration

Spring Boot thường tìm default bundle `classpath:/messages.properties`. **Nếu chỉ có `messages_vi.properties` và `messages_en.properties` mà thiếu default `messages.properties`, MessageSource auto-configuration có thể không được tạo như bạn chờ đợi.** Định nghĩa default file để có fallback có chủ đích.

Ví dụ cấu hình:

```properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
```

- `spring.messages.basename`: một hoặc nhiều nhóm bundle.
- `encoding=UTF-8`: giữ chữ có dấu Việt.
- `fallback-to-system-locale=false`: tránh kết quả phụ thuộc locale của hệ điều hành trong một số luồng fallback.
- MessageSource tìm theo mức đặc hiệu của locale khi có các file tương ứng như `messages_vi_VN.properties` và `messages_vi.properties`, sau đó fallback theo cấu hình và default bundle.

Người dùng chọn `vi-VN` vẫn có thể lấy key từ `messages_vi.properties` nếu không tồn tại file vùng cụ thể. Tên bundle thường sử dụng dấu underscore theo quy ước Java resource bundle, trong khi HTTP language tag dùng dấu gạch ngang (`vi-VN`). Không ghép đường dẫn file trực tiếp từ query parameter tùy ý.

### 7.2. Locale cũng ảnh hưởng số, ngày và validation messages

- `Formatter`, `@NumberFormat`, `@DateTimeFormat` có thể dùng locale cho parse/print ở web binding khi được cấu hình tương thích. Định dạng ngày/giờ còn cần timezone để ánh xạ đúng thời điểm.
- Constraint messages trong Jakarta Bean Validation có thể được tích hợp với Spring MessageSource hoặc bundle validation riêng, tùy cấu hình validator. Đừng giả định chỉ tạo `messages_vi.properties` là mọi message từ Hibernate Validator đều có bản dịch tiếng Việt tùy ý.
- Một request JSON API có thể chọn ngôn ngữ cho **thông báo lỗi** nhưng nên giữ error `code` ổn định để client logic không phụ thuộc văn bản bản địa hóa.
- Đối với HTML cache/CDN, response thay đổi theo `Accept-Language` nên cân nhắc header `Vary: Accept-Language`; theo cookie thì quan tâm cookie/session. Cache có thể phát nhầm ngôn ngữ giữa users nếu cache key không phản ánh ngôn ngữ.

## 8. Ví dụ hoàn chỉnh: Spring Boot 3 + Java 17 + CookieLocaleResolver

Ứng dụng nhỏ cung cấp:

- `GET /api/greeting`: JSON chứa language hiện tại và bản dịch từ MessageSource.
- `GET /api/greeting?lang=en` hoặc `?lang=vi`: interceptor đổi locale và phát cookie `SITE_LANG`.
- Request sau gửi cookie nhận lại cùng ngôn ngữ, không cần query parameter.
- `GET /api/context`: minh họa LocaleContext và time zone.
- `GET /welcome`: Thymeleaf render text bằng `#{greeting}` thay vì nhét một string dịch sẵn vào model.
- MockMvc chứng minh default/fallback, đổi ngôn ngữ, replay cookie, message rendering và context timezone.

Dùng **Spring Boot 3.3.13**, Java 17+ và Maven. Đây là mô hình **một cookie resolver được cấu hình rõ ràng**, không đồng thời tạo AcceptHeader/Session/Fixed resolvers trong cùng context.

### 8.1. Cấu trúc project

```text
locale-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/LocaleDemoApplication.java
    │   └── resources/
    │       ├── application.properties
    │       ├── messages.properties
    │       ├── messages_vi.properties
    │       ├── messages_en.properties
    │       └── templates/welcome.html
    └── test/java/example/LocaleDemoTest.java
```

### 8.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>locale-demo</artifactId>
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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

### 8.3. application.properties và các message bundles

```properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false

spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.cache=false
```

`src/main/resources/messages.properties`:

```properties
greeting=Welcome!
title=Locale demonstration
```

`src/main/resources/messages_vi.properties`:

```properties
greeting=Xin chào!
title=Ví dụ ngôn ngữ
```

`src/main/resources/messages_en.properties`:

```properties
greeting=Hello!
title=Language example
```

Mỗi key có một bản dịch. Với `lang=vi`, response là `"Xin chào!"`. Với `lang=en`, response là `"Hello!"`. Nếu language khác không có bundle, quy tắc fallback có thể dùng `messages.properties`; demo chỉ tập trung vào `vi` và `en`.

### 8.4. LocaleDemoApplication.java

Đặt toàn bộ code sau tại `src/main/java/example/LocaleDemoApplication.java`. Chỉ class main là public top-level class; các class còn lại package-private.

```java
package example;

import java.time.Duration;
import java.util.Locale;
import java.util.Map;
import java.util.TimeZone;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.MessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.LocaleResolver;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.i18n.CookieLocaleResolver;
import org.springframework.web.servlet.i18n.LocaleChangeInterceptor;
import org.springframework.web.servlet.support.RequestContextUtils;

@SpringBootApplication
public class LocaleDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LocaleDemoApplication.class, args);
    }
}

@Configuration
class LocaleWebConfig implements WebMvcConfigurer {

    // Tên bean "localeResolver" được DispatcherServlet nhận biết.
    @Bean
    LocaleResolver localeResolver() {
        CookieLocaleResolver resolver =
                new CookieLocaleResolver("SITE_LANG");

        // Default cụ thể giúp kết quả không phụ thuộc hệ điều hành.
        resolver.setDefaultLocale(Locale.forLanguageTag("vi"));
        resolver.setDefaultTimeZone(
                TimeZone.getTimeZone("Asia/Ho_Chi_Minh"));

        resolver.setCookieMaxAge(Duration.ofDays(30));
        resolver.setCookiePath("/");
        resolver.setCookieSameSite("Lax");
        resolver.setCookieHttpOnly(true);

        return resolver;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        LocaleChangeInterceptor change = new LocaleChangeInterceptor();
        change.setParamName("lang");
        change.setHttpMethods("GET");
        registry.addInterceptor(change);
    }
}

@RestController
class GreetingApiController {
    private final MessageSource messageSource;

    GreetingApiController(MessageSource messageSource) {
        this.messageSource = messageSource;
    }

    @GetMapping("/api/greeting")
    Map<String, String> greeting(HttpServletRequest request) {
        Locale locale = RequestContextUtils.getLocale(request);

        String message =
                messageSource.getMessage("greeting", null, locale);

        return Map.of(
                "language", locale.getLanguage(),
                "message", message);
    }

    @GetMapping("/api/context")
    Map<String, String> context(HttpServletRequest request) {
        Locale locale = RequestContextUtils.getLocale(request);
        TimeZone zone = RequestContextUtils.getTimeZone(request);

        return Map.of(
                "language", locale.getLanguage(),
                "timeZone", zone != null ? zone.getID() : "unset");
    }
}

@Controller
class WelcomePageController {
    @GetMapping("/welcome")
    String welcome() {
        return "welcome";
    }
}
```

Giải thích:

- Bean method `localeResolver()` có tên mặc định bằng tên method, đúng key mà `DispatcherServlet` tìm.
- `CookieLocaleResolver("SITE_LANG")` dùng constructor không deprecated trong Spring 6; không cần gọi `setCookieName(...)` đã deprecated từ 6.0.
- `setDefaultLocale(vi)` đặt locale fallback cố định. Trong demo **khi chưa có cookie**, giá trị này được ưu tiên; vì vậy `Accept-Language: en` một mình **không bảo đảm** lựa chọn tiếng Anh. Muốn coi header là ưu tiên, đừng cấu hình default cố định theo cách này hoặc chọn `AcceptHeaderLocaleResolver` tùy hợp đồng.
- `setDefaultTimeZone(...)` cho LocaleContext một time zone fallback. Nó không làm ngôn ngữ thay đổi.
- `LocaleChangeInterceptor` đọc `?lang=en`, gọi resolver cập nhật locale và đặt cookie cho các request sau.
- `MessageSource` giải quyết key `greeting` theo locale. Dù JSON body là API, vẫn có thể dùng locale để bản địa hóa thông điệp.
- Demo không mở rộng locale toàn cầu bằng singleton mutable; mỗi handler đọc từ request.

### 8.5. templates/welcome.html

File `src/main/resources/templates/welcome.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title th:text="#{title}">Demo</title>
</head>
<body>
  <h1 th:text="#{greeting}">Greeting</h1>
  <nav>
    <a th:href="@{/welcome(lang='vi')}">Tiếng Việt</a>
    <a th:href="@{/welcome(lang='en')}">English</a>
  </nav>
</body>
</html>
```

`th:text="#{greeting}"` tra cứu key trong `MessageSource` bằng locale đang hoạt động; `th:href="@{/welcome(lang='en')}"` tạo link chuyển ngôn ngữ. Template gán `lang="vi"` tĩnh để ví dụ dễ đọc, nhưng **không chính xác** khi người dùng đang xem tiếng Anh. Sản phẩm thực nên thêm `th:lang="${#locale.language}"` để HTML lang phản ánh ngôn ngữ được chọn. Nếu cần, thay thẻ `<html>` thành:

```html
<html xmlns:th="http://www.thymeleaf.org"
      th:lang="${#locale.language}">
```

Khi chạy, Thymeleaf tự bind variable `#locale` với locale hiện tại. Không nhầm `#{greeting}` (message expression) với `${#locale.language}` (variable expression).

### 8.6. Chạy và quan sát

Trong thư mục `locale-demo`:

```bash
mvn test
mvn spring-boot:run
```

Kiểm tra API:

```bash
curl -i http://localhost:8080/api/greeting
curl -i "http://localhost:8080/api/greeting?lang=en"
curl -i http://localhost:8080/api/context
```

Các response body JSON kỳ vọng:

- Không có cookie/param: `{"language":"vi","message":"Xin chào!"}` (thứ tự key JSON có thể khác).
- `?lang=en`: `{"language":"en","message":"Hello!"}` và header `Set-Cookie` cho `SITE_LANG`.
- `/api/context` với cấu hình mặc định: `{"language":"vi","timeZone":"Asia/Ho_Chi_Minh"}` nếu request không kèm cookie/param; timezone có thể được mang trong locale context khi resolver hỗ trợ.

Dùng cookie jar để chứng minh lựa chọn được giữ qua request:

```bash
curl -i -c locale-cookies.txt \
  "http://localhost:8080/api/greeting?lang=en"

curl -i -b locale-cookies.txt \
  http://localhost:8080/api/greeting

curl -i -b locale-cookies.txt \
  http://localhost:8080/welcome
```

Kết quả hai GET dùng cookie là ngôn ngữ tiếng Anh. Trên trang Thymeleaf, tiêu đề có `Language example` và `Hello!`. Nếu trực tiếp mở `http://localhost:8080/welcome?lang=vi`, interceptor sẽ cập nhật cookie sang tiếng Việt.

**Lưu ý:** lệnh `curl` ở trên dành cho shell hỗ trợ dấu nối dòng `\`; trên Windows PowerShell có thể dùng `curl.exe` và đưa tham số vào một dòng.

### 8.7. MockMvc: kiểm tra cookie và ngôn ngữ

File `src/test/java/example/LocaleDemoTest.java`:

```java
package example;

import jakarta.servlet.http.Cookie;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class LocaleDemoTest {
    @Autowired
    MockMvc mvc;

    @Test
    void fallbackLocaleIsVietnamese() throws Exception {
        mvc.perform(get("/api/greeting"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.language").value("vi"))
            .andExpect(jsonPath("$.message").value("Xin chào!"));
    }

    @Test
    void queryParameterChangesLocaleOnCurrentRequest()
            throws Exception {
        mvc.perform(get("/api/greeting").param("lang", "en"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.language").value("en"))
            .andExpect(jsonPath("$.message").value("Hello!"));
    }

    @Test
    void chosenLocaleIsPersistedInCookie() throws Exception {
        MvcResult changed =
                mvc.perform(get("/api/greeting").param("lang", "en"))
                   .andExpect(status().isOk())
                   .andReturn();

        String header = changed.getResponse().getHeader("Set-Cookie");
        assertNotNull(header);
        assertTrue(header.startsWith("SITE_LANG="));

        // Parse duy nhất cặp name=value đầu trong header Set-Cookie;
        // demo cookie chỉ chứa language tag, không có dấu '=' nội bộ.
        String value = header.split(";", 2)[0].split("=", 2)[1];

        mvc.perform(get("/api/greeting")
                    .cookie(new Cookie("SITE_LANG", value)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.language").value("en"))
            .andExpect(jsonPath("$.message").value("Hello!"));
    }

    @Test
    void defaultTimeZoneIsResolvedFromLocaleContext()
            throws Exception {
        mvc.perform(get("/api/context"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.language").value("vi"))
            .andExpect(jsonPath("$.timeZone")
                    .value("Asia/Ho_Chi_Minh"));
    }

    @Test
    void thymeleafRendersLocalizedMessage() throws Exception {
        mvc.perform(get("/welcome").param("lang", "en"))
            .andExpect(status().isOk())
            .andExpect(view().name("welcome"))
            .andExpect(content().string(
                    containsString("<h1>Hello!</h1>")));
    }

    @Test
    void apiResponseIsJsonNotAView() throws Exception {
        mvc.perform(get("/api/greeting").param("lang", "en"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.message").value("Hello!"));
    }
}
```

Chạy `mvn test`. Bộ test chứng minh locale mặc định, thay đổi trên cùng request, cookie được gửi và dùng lại, time zone fallback, Thymeleaf sử dụng message bundle và JSON API không bị nhầm với template. Mỗi request MockMvc mặc định không tự tái sử dụng cookie từ request trước; test cố tình copy giá trị cookie sang request mới để mô phỏng browser.

Nếu deploy với reverse proxy, cookie policy có thể thêm `Secure`/`Domain` hoặc thay cách viết header. Vì vậy trong ứng dụng production, ưu tiên integration test đầy đủ trên HTTP client thực tế cho lifecycle của cookie, không chỉ MockMvc.

## 9. Khi nào nên dùng header, cookie, session hoặc tài khoản?

### 9.1. REST API stateless

Client có thể gửi:

```http
GET /api/products/7 HTTP/1.1
Accept-Language: en
```

Server dùng `AcceptHeaderLocaleResolver` và `MessageSource` để bản địa hóa thông điệp, giữ mã lỗi JSON ổn định. Không cần server session. Với API nhiều clients, phân biệt locale yêu cầu và ngôn ngữ thực hỗ trợ; không nên trả toàn bộ nội dung nghiệp vụ khác đi chỉ vì Accept-Language nếu hợp đồng không nói.

Một số API chọn header riêng hoặc user profile; phải định nghĩa thứ tự ưu tiên, nhất là khi cùng tồn tại cookie và Accept-Language. Dữ liệu quốc tế hóa không nên làm thay đổi ID, enum code hay tiền tệ một cách mơ hồ.

### 9.2. Website server-rendered

`CookieLocaleResolver` tiện cho website không muốn tạo session chỉ để nhớ language. Dùng links/buttons để chọn locale, rồi render Thymeleaf bằng message expressions. Nếu người dùng đăng nhập, có thể lưu ngôn ngữ vào profile; cookie đóng vai trò cache/preference tạm.

### 9.3. Website đã dùng HttpSession

`SessionLocaleResolver` thích hợp khi session là phần của thiết kế. Locale lựa chọn được giữ cho tới khi session hết hạn. Nếu session bị đổi do login/logout hoặc load balancing, xử lý đồng bộ profile/cookie/session một cách nhất quán.

### 9.4. Ứng dụng cố định ngôn ngữ

`FixedLocaleResolver` thích hợp cho dịch vụ chỉ có một ngôn ngữ hoặc môi trường kiểm thử cố định. Không thêm LocaleChangeInterceptor nếu không có nhu cầu đổi locale động.

### 9.5. Chiến lược ưu tiên rõ ràng

Một ví dụ về **chính sách sản phẩm tự định nghĩa** (không phải thứ tự mặc định bắt buộc của Spring):

```text
1. Lựa chọn explicit của user đã lưu trong profile
2. Cookie language do người dùng tự chọn
3. Accept-Language từ HTTP request
4. Locale mặc định của sản phẩm, ví dụ vi
```

Cần cài đặt chính sách trong resolver/custom logic một cách rõ ràng, nhất là khi ngôn ngữ hỗ trợ chỉ có `vi`/`en`. Không mong Spring tự phối hợp cả profile, cookie, header theo thứ tự trên nếu chưa lập trình.

## 10. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `?lang=en` gây `UnsupportedOperationException` | Dùng LocaleChangeInterceptor với AcceptHeader/Fixed resolver | Chuyển sang Cookie/Session hoặc không cho đổi locale động |
| Dùng `LocaleContextResolver` nhưng import sai | Import từ `org.springframework.web.server.i18n` của WebFlux | Dùng `org.springframework.web.servlet.LocaleContextResolver` cho Spring MVC |
| Header `en-GB` không chọn ngôn ngữ mong muốn | Supported locale cấu hình chỉ `en-US` | Cấu hình ngôn ngữ-only `en` hoặc vùng tương thích |
| Browser gửi `Accept-Language: en` nhưng vẫn ra `vi` | Cookie cũ hoặc `defaultLocale(vi)` ưu tiên | Kiểm tra resolver, cookie và fallback order |
| `MessageSource` không xuất hiện | Thiếu file `messages.properties` mặc định hoặc sai basename | Thêm bundle mặc định và kiểm tra `spring.messages.*` |
| UI có chữ `??greeting??` hay lỗi missing code | Thiếu key trong bundle, bundle không load | Đối chiếu key, basename và language suffix |
| Chữ tiếng Việt thành ký tự lỗi | File/response encoding khác nhau | UTF-8 từ editor, bundle, HTML meta tới response |
| Time zone luôn null | Chỉ có basic LocaleResolver hoặc chưa cấu hình time zone | Dùng LocaleContextResolver + default/user timezone |
| `en-US` hiển thị ngày không đúng time zone | Locale không phải time zone | Dùng `ZoneId`/`TimeZone` riêng |
| Đổi locale nhưng background thread vẫn theo ngôn ngữ cũ | LocaleContextHolder không tự truyền qua thread | Truyền locale vào tác vụ hoặc context propagation |
| HTML CDN phát nhầm ngôn ngữ giữa người dùng | Cache không vary theo language/cookie | Bổ sung cache key/Vary hoặc tắt shared caching |
| User gửi locale kỳ lạ và UI fallback bất ngờ | Không whitelist locale hỗ trợ | Kiểm tra danh sách hỗ trợ, thông báo/fallback có chủ ý |
| Test thay đổi cookie nhưng request sau vẫn mặc định | MockMvc không giả lập browser cookie jar | Truyền cookie sang request tiếp theo |
| Dùng `Locale.US` cho toàn bộ người Việt | Nhầm language/region với locale UI | Dùng language tag thích hợp và bundle có fallback rõ |

### 10.1. Debug theo từng tầng

1. Xem request có `Accept-Language`, cookie `SITE_LANG` hoặc query `lang` hay không.
2. Xác định **đúng resolver bean** tên `localeResolver` được DispatcherServlet dùng. Kiểm tra kiểu bean và các giá trị mặc định.
3. Nếu có `LocaleChangeInterceptor`, kiểm tra nó được đăng ký trong `WebMvcConfigurer#addInterceptors` và tên parameter khớp.
4. Đọc resolved locale bằng `RequestContextUtils.getLocale(request)`; nếu cần context timezone thì `getTimeZone(request)`.
5. Kiểm tra `messages.properties`, `messages_vi.properties`, `messages_en.properties`, key và encoding.
6. Nếu controller trả đúng message nhưng Thymeleaf sai, kiểm tra template expression `#{...}`, theme, model, view name và template cache.
7. Với API, kiểm tra error `code` độc lập với localized `message` và client cache policy.
8. Viết MockMvc test có cả query param, cookie và request không có lựa chọn.

### 10.2. Hai ví dụ sai và sửa

**Sai:**

```java
@Bean
LocaleResolver localeResolver() {
    return new AcceptHeaderLocaleResolver();
}

@Override
public void addInterceptors(InterceptorRegistry registry) {
    LocaleChangeInterceptor interceptor = new LocaleChangeInterceptor();
    interceptor.setParamName("lang");
    registry.addInterceptor(interceptor);
}
```

Khi URL chứa `?lang=en`, interceptor gọi `setLocale` trên resolver không hỗ trợ, phát sinh lỗi. Đây là đoạn minh họa để nhận diện lỗi, **không** đặt vào project chạy.

**Đúng khi muốn user đổi ngôn ngữ và lưu lại:**

```java
@Bean
LocaleResolver localeResolver() {
    return new CookieLocaleResolver("SITE_LANG");
}
```

Thêm interceptor như project mục 8 và cấu hình cookie/security nếu cần.

## 11. Bảo mật, hiệu năng và trải nghiệm quốc tế hóa

- **XSS:** bản dịch từ message bundles có thể chứa markup nếu ứng dụng cho phép; không render dữ liệu từ người dùng bằng HTML unescaped. Thymeleaf `th:text` mặc định escape text.
- **Open redirects:** endpoint đổi locale không nên chuyển đến URL tùy ý do request cung cấp. Chỉ redirect về route/host cho phép.
- **Cookie:** chỉ chứa preference ít nhạy cảm, chọn `SameSite`/`Secure`/`HttpOnly`/maxAge/path theo chính sách; không dùng cookie language để quyết định quyền.
- **Cache:** response HTML thay đổi theo locale; cấu hình cache theo cookie/header hoặc dùng URL ngôn ngữ tường minh để dễ cache.
- **SEO:** website công khai đa ngôn ngữ có thể chọn URL ngôn ngữ như `/vi/...` và `/en/...`, kết hợp `hreflang`/canonical theo chiến lược SEO. Cookie locale không nhất thiết là lựa chọn tốt nhất để crawl mọi biến thể.
- **A11y:** thuộc tính HTML `lang` phải phản ánh nội dung đang hiển thị; trong ví dụ ở trên có thể dùng `th:lang` động.
- **I18n message design:** tránh nối câu từ nhiều mảnh literal; dùng placeholders/pluralization phù hợp công cụ và dịch thuật theo ngữ cảnh.
- **Timezone & currency:** tách `Locale` khỏi time zone và currency thực tế. `Locale.US` không có nghĩa người dùng thanh toán bằng USD; nghiệp vụ phải có nguồn dữ liệu tin cậy riêng.
- **Validation:** đừng đổi field name hoặc error code theo ngôn ngữ; chỉ đổi thông điệp thân thiện hiển thị.
- **Operations:** log ngôn ngữ đã chọn ở mức không nhạy cảm để phân tích lỗi phân phối bundle; không log cookie nguyên vẹn kèm token của request.

## 12. Tự kiểm tra

1. `LocaleResolver` có tự dịch text không? **Không.** Nó chọn locale; MessageSource/template làm công việc tra thông điệp.
2. `LocaleContextResolver` kế thừa giao diện nào? **`LocaleResolver`**, thêm phương thức cho `LocaleContext`.
3. Có thể dùng `LocaleContextResolver` của WebFlux trong Servlet MVC không? **Không**, hai API ở package/loại request khác nhau.
4. `AcceptHeaderLocaleResolver` có hỗ trợ `setLocale` từ query parameter không? **Không**, vì header do client quản lý.
5. Nếu muốn user chọn tiếng Anh và nhớ qua nhiều request mà không dùng server session, chọn gì? **CookieLocaleResolver**.
6. Nếu muốn nhớ lựa chọn trong phiên HttpSession, chọn gì? **SessionLocaleResolver**.
7. Khi ứng dụng luôn chỉ hiển thị tiếng Việt, resolver phù hợp? **FixedLocaleResolver** hoặc chính sách locale cố định.
8. Vì sao supportedLocales chỉ có `en-US` có thể không match `en-GB`? **So khớp language+country**, nên bổ sung `en` nếu muốn fallback theo ngôn ngữ.
9. `vi-VN` có đồng nghĩa múi giờ Asia/Ho_Chi_Minh không? **Không**; locale và timezone là dữ liệu riêng.
10. Khi dùng Thymeleaf, `#{greeting}` khác `${name}` thế nào? **`#{...}` tra message code**, còn `${...}` lấy model variable.
11. Vì sao `messages.properties` quan trọng trong Boot? **Bundle mặc định giúp auto-config và fallback hoạt động như dự kiến**.
12. `LocaleChangeInterceptor` đọc param tên gì mặc định? **`locale`**; có thể dùng `setParamName("lang")`.
13. Nếu cookie ngôn ngữ đã lưu là `en` nhưng header là `vi`, cái nào được dùng? **Tùy resolver/chính sách**; với CookieLocaleResolver, cookie thường ưu tiên.
14. `MockMvc` có tự giữ cookie từ request trước như browser không? **Không mặc định**; phải truyền cookie ở request sau.
15. Timezone lấy bằng API nào ở Servlet MVC? **`RequestContextUtils.getTimeZone(request)`**, trả null nếu không có.
16. Vì sao cần `Vary: Accept-Language`/cache theo cookie? **Để tránh trả bản dịch của người này cho người khác**.
17. Dùng `LocaleContextHolder` trong một thread pool có luôn đọc được locale request không? **Không chắc**, cần context propagation/truyền tường minh.
18. Khi client gửi `lang=fr` nhưng chỉ có bundles vi/en, có chắc server ném lỗi không? **Không.** Resolver có thể chấp nhận locale, còn MessageSource fallback nếu không có bundle; phải whitelist nếu muốn từ chối.
19. Nếu dịch tiêu đề nhưng HTML vẫn `<html lang="vi">` cho bản tiếng Anh, có vấn đề gì? **Có**, lang không phản ánh nội dung và ảnh hưởng accessibility/SEO.
20. Làm sao chứng minh i18n hoạt động end-to-end? **Test resolver selection, MessageSource output, cookie replay và template render theo locale**.

## 13. Nguồn tham khảo chính thức

- [Spring Framework 6.2 — Locale Resolution](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/localeresolver.html): các resolver, cookie/session, locale change interceptor.
- [LocaleResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/servlet/LocaleResolver.html): hai phương thức `resolveLocale`/`setLocale`.
- [LocaleContextResolver (Servlet) Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/servlet/LocaleContextResolver.html): time zone-aware context và thay đổi context.
- [AcceptHeaderLocaleResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/servlet/i18n/AcceptHeaderLocaleResolver.html): `supportedLocales`, matching, hạn chế `setLocale`.
- [CookieLocaleResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/servlet/i18n/CookieLocaleResolver.html): cấu hình cookie, default locale/time zone.
- [LocaleChangeInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/servlet/i18n/LocaleChangeInterceptor.html): parameter name, method filter, invalid-locale handling.
- [Spring Boot — Internationalization](https://docs.spring.io/spring-boot/3.3/reference/features/internationalization.html): tự cấu hình MessageSource từ bundles và properties.
- [Thymeleaf + Spring Tutorial](https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html): message expressions `#{...}`, variables và Spring MVC integration.
- [MDN Accept-Language](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Language): HTTP language preference/q-values.

**Ghi nhớ:** `LocaleResolver` chọn **locale** cho request. `LocaleContextResolver` mở rộng bằng **LocaleContext và tùy chọn time zone**. `LocaleChangeInterceptor` chỉ phù hợp với resolver **cho phép thay đổi locale**, như cookie/session. `MessageSource` và template engine mới thực sự tạo ra văn bản bản địa hóa. Phải định nghĩa rõ thứ tự ưu tiên giữa header, cookie, session và profile, đồng thời kiểm thử thay đổi ngôn ngữ qua nhiều request.
