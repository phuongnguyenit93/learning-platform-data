# MessageSource, Locale và bản địa hóa nội dung giao diện trong Spring Boot

## 1. Vấn đề cần giải quyết

Một ứng dụng web thường phải hiển thị cùng một giao diện cho người dùng Việt Nam, Anh, Mỹ hoặc các khu vực khác. Thay vì viết trực tiếp chữ “Đăng nhập”, “Welcome”, “Không tìm thấy dữ liệu” vào nhiều controller/template, Spring cho phép tách **nội dung có thể dịch** ra khỏi mã nguồn và chọn nội dung theo **Locale** của request.

Ba khái niệm có vai trò khác nhau:

- **Internationalization (i18n)**: thiết kế ứng dụng có thể hỗ trợ nhiều ngôn ngữ và quy ước vùng miền mà không cần viết lại logic; ví dụ dùng mã thông điệp `page.title` thay cho một chuỗi cố định.
- **Localization (l10n)**: cung cấp bản dịch, format số/ngày/tiền tệ và điều chỉnh trải nghiệm cho một locale cụ thể; ví dụ `vi-VN`, `en-US`, `en-GB`.
- **Locale**: đối tượng `java.util.Locale` mô tả ngôn ngữ, vùng và có thể thêm script/variant. Ví dụ `vi` chỉ tiếng Việt; `vi-VN` chỉ tiếng Việt dùng trong ngữ cảnh Việt Nam. **Locale không phải múi giờ (time zone)**, không phải mã hóa UTF-8 và cũng không phải quyền truy cập người dùng.

**Hai câu hỏi phải giải quyết riêng:**

1. **Request này chọn ngôn ngữ nào?** Spring MVC dùng `LocaleResolver`/`LocaleContextResolver`, thường lấy từ `Accept-Language` hoặc từ session/cookie tùy cấu hình.
2. **Với ngôn ngữ ấy, câu “Xin chào” là gì?** Spring `MessageSource` tìm mã thông điệp trong resource bundle phù hợp và thay các tham số.

Thymeleaf, JSP, giao diện render trên server, thông báo lỗi validation và cả nội dung API có thể sử dụng hệ thống này. Bản địa hóa **không đồng nghĩa tự động dịch văn bản**: mỗi bản dịch vẫn cần được cung cấp, kiểm thử và duy trì.

## 2. Dòng xử lý khi browser yêu cầu một trang đã bản địa hóa

```text
Browser (Accept-Language: vi-VN,vi;q=0.9,en;q=0.8)
                      |
                   HTTP GET /
                      |
                 Spring MVC
               DispatcherServlet
                      |
            LocaleResolver xác định
                Locale vi-VN
                      |
          Controller -> model / view
                      |
          Thymeleaf: #{page.title}
                      |
                  MessageSource
                      |
      i18n/messages_vi_VN.properties (nếu có)
                    -> messages_vi.properties
                    -> messages.properties
                      |
                 "Chào mừng"
                      |
            HTML được render và trả về
```

Sơ đồ thể hiện thứ tự ưu tiên **khái quát** khi `fallback-to-system-locale=false`. JDK `ResourceBundle` và cấu hình Spring có thể áp dụng thêm quy tắc fallback; không nên suy luận thứ tự từ mỗi tên file nếu bật fallback về locale hệ thống.

Lưu ý: header **`Accept-Language`** biểu thị ngôn ngữ ưu tiên; header **`Accept`** biểu thị kiểu nội dung như `text/html` hoặc `application/json`. Hai header này phục vụ hai mục đích khác nhau.

## 3. `MessageSource` là gì?

`org.springframework.context.MessageSource` là giao diện tra cứu thông điệp theo **code + arguments + locale**. Spring `ApplicationContext` cũng triển khai `MessageSource`; khi có bean tên `messageSource`, context ủy quyền việc tra cứu cho bean đó. Spring Boot có thể tự cấu hình bean `MessageSource` từ các file `.properties` trên classpath.

Ba phương thức quan trọng:

```java
// 1. Có thông điệp dự phòng nếu code không tồn tại.
String a = messages.getMessage(
        "greeting.user", new Object[] {"Lan"}, "Hello!", locale);

// 2. Không cung cấp thông điệp dự phòng:
//    ném NoSuchMessageException nếu không có code.
String b = messages.getMessage(
        "greeting.user", new Object[] {"Lan"}, locale);

// 3. Dùng MessageSourceResolvable, thường gặp trong BindingResult.
String c = messages.getMessage(resolvable, locale);
```

Đây là **mã minh họa**, chưa chạy độc lập vì biến `messages`, `locale`, `resolvable` phải được cung cấp.

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `code` | Khóa ổn định trong bundle | `greeting.user` |
| `args` | Giá trị được chèn vào placeholder | `new Object[] {"Lan"}` |
| `locale` | Ngôn ngữ/vùng muốn tra cứu | `Locale.forLanguageTag("vi-VN")` |
| `defaultMessage` | Chuỗi dự phòng khi không tìm thấy key | `"Xin chào!"` |
| `ResourceBundleMessageSource` | Hiện thực dựa trên resource bundle chuẩn Java | `i18n/messages_vi.properties` |
| `ReloadableResourceBundleMessageSource` | Hiện thực linh hoạt hơn về resource location và tải lại file | Hợp với cấu hình message source tùy chỉnh |

Trong Spring Boot thông thường, **ưu tiên dùng auto-configuration** thay vì tự định nghĩa `@Bean MessageSource`. Chỉ tạo bean thủ công nếu có nhu cầu đặc biệt về nguồn lưu trữ, nạp lại hoặc cách fallback.

### Code, message và giá trị tham số

Ví dụ `messages_vi.properties`:

```properties
greeting.user=Xin chào, {0}!
cart.items=Bạn có {0,number,integer} sản phẩm.
```

Khi gọi:

```java
Locale vi = Locale.forLanguageTag("vi-VN");
String value = messages.getMessage(
        "greeting.user", new Object[] {"Lan"}, vi);
// value = "Xin chào, Lan!"
```

Placeholder `{0}` là phần tử đầu tiên của mảng args, `{1}` là phần tử tiếp theo. Spring dùng **`java.text.MessageFormat`** để định dạng tham số theo locale; có thể dùng các kiểu như `{0,number,integer}` hoặc `{0,date,short}`. Đây là cú pháp của `MessageFormat`, **không phải** cú pháp `${...}` của Spring Expression Language.

### Dấu nháy đơn trong `MessageFormat`

Dấu nháy đơn có ý nghĩa đặc biệt. Khi một message được áp dụng `MessageFormat`, muốn hiển thị một dấu `'` phải viết `''` trong mẫu:

```properties
sample.quote=Don''t remove ''{0}''.
```

Nếu truyền `new Object[]{"demo"}` thì chuỗi được format là `Don't remove 'demo'.`. Với các message **không có args**, Spring mặc định có thể không parse `MessageFormat` (`spring.messages.always-use-message-format=false`). Vì vậy hãy có quy ước rõ ràng và kiểm thử cả message có/không có tham số; tránh để dấu nháy sinh lỗi khó tìm sau khi thêm placeholder.

## 4. Resource bundle: tổ chức file và quy tắc tìm bản dịch

### 4.1. Cấu trúc file

Với basename `i18n/messages`, tổ chức:

```text
src/main/resources/
├── application.properties
└── i18n/
    ├── messages.properties
    ├── messages_vi.properties
    ├── messages_en.properties
    └── messages_en_GB.properties   (tùy chọn)
```

Ý nghĩa:

- `messages.properties`: **base bundle** và nguồn dự phòng chung; nên luôn có.
- `messages_vi.properties`: thông điệp tiếng Việt.
- `messages_en.properties`: thông điệp tiếng Anh.
- `messages_en_GB.properties`: phiên bản tiếng Anh Anh khi cần từ ngữ riêng (ví dụ “postcode”).
- Có thể thêm `messages_vi_VN.properties` nếu phân biệt tiếng Việt theo vùng.

Tên file tuân thủ quy ước `ResourceBundle`, thường dùng dấu gạch dưới trong tên file (`vi_VN`), trong khi HTTP `Accept-Language`/BCP 47 thường dùng dấu gạch nối (`vi-VN`). Không nên tạo `messages_vi-VN.properties` rồi kỳ vọng JDK tìm được như bundle thông thường.

### 4.2. Bật auto-configuration đúng cách

`src/main/resources/application.properties`:

```properties
spring.messages.basename=i18n/messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
```

Trong dự án dùng Spring Boot 3.5.x, đây là các property hợp lệ. `spring.messages.basename` **không ghi phần mở rộng `.properties`**; nó định vị nhóm bundle trên classpath. Boot hỗ trợ nhiều basename, ví dụ:

```properties
spring.messages.basename=i18n/messages,i18n/errors
```

Nếu mỗi basename có file riêng, tránh dùng trùng key không chủ đích vì thứ tự tra cứu có thể ảnh hưởng bundle được chọn.

**Điều kiện dễ bị bỏ qua:** Boot tự cấu hình `MessageSource` khi có **file base không có hậu tố ngôn ngữ** cho ít nhất một basename đã cấu hình. Nếu chỉ có `messages_vi.properties`, không có `messages.properties`, auto-configuration có thể không được kích hoạt. Tạo file base kể cả khi nhiều key sẽ được dịch trong các file khác.

### 4.3. Quy tắc fallback thực dụng

Giả sử `spring.messages.fallback-to-system-locale=false` và code gọi với `Locale.forLanguageTag("vi-VN")`:

1. Tìm bản cụ thể cho `vi_VN` nếu có.
2. Nếu không, tìm bản `vi`.
3. Nếu vẫn không có key, tìm `messages.properties`.
4. Nếu code không xuất hiện ở đâu, dùng `defaultMessage` của lời gọi; nếu không có default, ném `NoSuchMessageException` (trừ khi đã cấu hình dùng code làm thông điệp mặc định).

Ví dụ:

```properties
# messages.properties
page.title=Welcome
page.footer=Example application
```

```properties
# messages_vi.properties
page.title=Chào mừng
```

Với `vi-VN`, `page.title` là “Chào mừng” nhưng `page.footer` vẫn là “Example application”. Fallback theo **từng key**, không phải cứ thiếu cả file là mới có fallback.

Một vài cấu hình hữu ích:

| Property | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `spring.messages.basename` | Chỉ định các bundle nguồn | Mặc định `messages` ở classpath root |
| `spring.messages.encoding` | Mã hóa file | Mặc định `UTF-8` trong Boot hiện đại |
| `spring.messages.fallback-to-system-locale` | Có thử locale hệ điều hành khi không tìm được bundle phù hợp? | Đặt `false` để fallback về base bundle dễ dự đoán |
| `spring.messages.cache-duration` | Thời hạn cache bundle | Cân nhắc khi phát triển; production thường đóng gói file cùng JAR |
| `spring.messages.always-use-message-format` | Luôn áp `MessageFormat` kể cả khi không có args | Cần đồng nhất cách escape dấu nháy |
| `spring.messages.use-code-as-default-message` | Hiển thị code khi thiếu bản dịch | Hữu ích để debug, không nên che thiếu bản dịch ở production |

Dù Java có quy ước lịch sử với encoding của `.properties`, khi Spring Boot đã cấu hình `spring.messages.encoding=UTF-8` thì file được đọc theo UTF-8. Hãy bảo đảm editor, pipeline build và repository thật sự lưu file ở UTF-8.

## 5. Chọn `Locale` cho request trong Spring MVC

**`MessageSource` không tự quyết định locale của request.** Spring MVC sử dụng `LocaleResolver`, được tích hợp với `DispatcherServlet`, để xác định locale cho xử lý web.

### 5.1. Mặc định: `Accept-Language`

Trong Spring Boot MVC thông thường, locale resolver mặc định dựa trên header `Accept-Language`. Ví dụ:

```http
GET / HTTP/1.1
Host: localhost:8080
Accept-Language: vi-VN,vi;q=0.9,en;q=0.8
```

Khi không có cơ chế ghi đè nào khác, Spring có thể chọn `vi-VN` để tra cứu message. Tuy nhiên server **không bắt buộc dịch sang mọi locale trình duyệt yêu cầu**; việc tìm bundle và fallback vẫn quyết định nội dung thực tế.

`AcceptHeaderLocaleResolver` **không hỗ trợ thay đổi locale thông qua `setLocale`**, vì ngôn ngữ do client gửi trong header. Vì vậy nếu thêm `LocaleChangeInterceptor` xử lý `?lang=vi` nhưng vẫn giữ resolver chỉ đọc `Accept-Language`, việc chuyển ngôn ngữ sẽ không hoạt động như mong muốn và có thể ném `UnsupportedOperationException`. Nếu muốn người dùng chủ động chọn ngôn ngữ trong giao diện, dùng resolver có khả năng lưu thay đổi, ví dụ session/cookie.

### 5.2. `SessionLocaleResolver` và `CookieLocaleResolver`

| Resolver | Nguồn locale | Ưu điểm | Điều cần cân nhắc |
| --- | --- | --- | --- |
| `AcceptHeaderLocaleResolver` | HTTP `Accept-Language` | Tự nhiên cho API; không lưu trạng thái ngôn ngữ trên server | Không thay được bằng `LocaleChangeInterceptor` |
| `SessionLocaleResolver` | `HttpSession`, nếu chưa có thì fallback tương ứng | Dễ làm nút chuyển ngôn ngữ cho giao diện server-rendered | Phụ thuộc session, hết hạn/mất khi session mất |
| `CookieLocaleResolver` | Cookie phía client | Có thể giữ lựa chọn giữa các phiên nếu cấu hình phù hợp | Cần chính sách cookie/consent/bảo mật và giá trị hợp lệ |
| Resolver cố định | Một locale được cấu hình | Dùng cho ứng dụng một ngôn ngữ hoặc test | Không cá nhân hóa theo request |

`LocaleChangeInterceptor` phát hiện query parameter (mặc định `locale`, có thể đổi thành `lang`) và nhờ resolver cập nhật locale. Interceptor chỉ có ý nghĩa khi resolver hỗ trợ thay đổi trạng thái.

**Không dùng locale như dữ liệu đáng tin về quốc gia hoặc danh tính.** Client có thể tự chọn header, cookie và query parameter; nó không phải bằng chứng địa lý, chính sách thuế hay quyền được phép xem dữ liệu.

### 5.3. Ngôn ngữ, vùng và múi giờ

`Locale.forLanguageTag("en-GB")` và `Locale.forLanguageTag("en-US")` đều là tiếng Anh nhưng có thể khác cách viết và format. `TimeZone`/`ZoneId` là khái niệm khác: người dùng thích tiếng Việt nhưng đang sống tại London vẫn có thể muốn hiển thị lịch ở `Europe/London`.

Để hiển thị ngày/giờ đúng, phải chọn cả **Locale cho định dạng** lẫn **ZoneId cho thời điểm**. Không truyền một `LocalDateTime` không timezone vào format rồi mặc nhiên coi là thời điểm tuyệt đối.

## 6. Ví dụ chạy được: Spring Boot MVC + Thymeleaf + chuyển ngôn ngữ

Ví dụ hoàn chỉnh dùng **Java 17**, **Maven**, **Spring Boot 3.5.16**, Spring MVC và Thymeleaf. Chọn phiên bản cụ thể để có thể tái hiện POM; khi triển khai production, chọn dòng Spring Boot đang được hỗ trợ và kiểm tra compatibility. Ở Boot 4.x, tên một số starter/API có thể khác; không trộn dependency từ hai major versions.

Ứng dụng có hai chức năng:

- `GET /`: trả trang Thymeleaf có tiêu đề, mô tả và câu chào được dịch.
- `GET /api/greeting?name=Lan`: trả text từ `MessageSource` theo locale request.
- `GET /?lang=vi` và `GET /?lang=en`: đổi locale được lưu trong HTTP session.

### 6.1. Cấu trúc project

```text
i18n-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/i18ndemo/
    │   ├── I18nDemoApplication.java
    │   ├── WebLocaleConfig.java
    │   └── PageController.java
    └── resources/
        ├── application.properties
        ├── i18n/
        │   ├── messages.properties
        │   ├── messages_en.properties
        │   └── messages_vi.properties
        └── templates/
            └── home.html
```

### 6.2. Maven POM đầy đủ

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>i18n-demo</artifactId>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

Spring Boot parent quản lý phiên bản Spring Framework, Thymeleaf và các dependency cần thiết. Không cần khai báo phiên bản riêng cho Thymeleaf nếu dùng starter/BOM tương ứng.

### 6.3. Java main

Tệp `src/main/java/com/example/i18ndemo/I18nDemoApplication.java`:

```java
package com.example.i18ndemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class I18nDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(I18nDemoApplication.class, args);
    }
}
```

`@SpringBootApplication` quét các class trong cùng package và subpackage; do đó controller/config bên cạnh được phát hiện.

### 6.4. Cấu hình chọn và đổi locale

Tệp `src/main/java/com/example/i18ndemo/WebLocaleConfig.java`:

```java
package com.example.i18ndemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.LocaleResolver;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.i18n.LocaleChangeInterceptor;
import org.springframework.web.servlet.i18n.SessionLocaleResolver;

@Configuration
public class WebLocaleConfig implements WebMvcConfigurer {

    @Bean
    public LocaleResolver localeResolver() {
        return new SessionLocaleResolver();
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        LocaleChangeInterceptor change = new LocaleChangeInterceptor();
        change.setParamName("lang");
        registry.addInterceptor(change);
    }
}
```

`SessionLocaleResolver` lưu lựa chọn vào `HttpSession`. Trước khi user chủ động chọn, nó có thể dùng request locale (thường xuất phát từ `Accept-Language`). Khi có `?lang=vi` hoặc `?lang=en`, interceptor gọi `setLocale` và trang được render bằng locale mới. Không cần `@EnableWebMvc`: annotation này có thể làm thay đổi auto-configuration MVC mà ví dụ đang dựa vào.

Trong sản phẩm thực, nên giới hạn danh sách ngôn ngữ cho phép, ví dụ chỉ `vi` và `en`; tránh tin vô điều kiện một chuỗi locale tùy ý do client gửi.

### 6.5. Controller có cả trang HTML và API text

Tệp `src/main/java/com/example/i18ndemo/PageController.java`:

```java
package com.example.i18ndemo;

import java.util.Locale;

import org.springframework.context.MessageSource;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class PageController {

    private final MessageSource messages;

    public PageController(MessageSource messages) {
        this.messages = messages;
    }

    @GetMapping("/")
    public String home(Model model, Locale locale) {
        model.addAttribute("visitorName", "Lan");
        model.addAttribute("itemCount", 12);
        model.addAttribute("activeLanguage", locale.toLanguageTag());
        return "home";
    }

    @ResponseBody
    @GetMapping(value = "/api/greeting", produces = "text/plain;charset=UTF-8")
    public String greeting(
            @RequestParam(defaultValue = "Lan") String name,
            Locale locale) {
        return messages.getMessage(
                "greeting.user",
                new Object[] {name},
                locale
        );
    }
}
```

Ở handler `home`, `Locale locale` là đối số MVC resolve theo request, còn `Model` chuyển dữ liệu cho Thymeleaf. Ở handler `greeting`, `MessageSource` tìm đúng thông điệp theo locale; `@ResponseBody` trả nội dung thẳng về HTTP thay vì tìm template. `produces` chỉ định UTF-8 để response tiếng Việt rõ ràng.

### 6.6. Cấu hình và message bundle

`src/main/resources/application.properties`:

```properties
spring.messages.basename=i18n/messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
```

`src/main/resources/i18n/messages.properties` (bản base):

```properties
page.title=Welcome
page.description=This page uses Spring Boot and MessageSource.
greeting.user=Hello, {0}!
items.summary=You have {0,number,integer} items.
language.vi=Vietnamese
language.en=English
page.footer=Localization demo
```

`src/main/resources/i18n/messages_en.properties`:

```properties
page.title=Welcome
page.description=This page uses Spring Boot and MessageSource.
greeting.user=Hello, {0}!
items.summary=You have {0,number,integer} items.
language.vi=Vietnamese
language.en=English
```

`src/main/resources/i18n/messages_vi.properties`:

```properties
page.title=Chào mừng
page.description=Trang này dùng Spring Boot và MessageSource.
greeting.user=Xin chào, {0}!
items.summary=Bạn có {0,number,integer} sản phẩm.
language.vi=Tiếng Việt
language.en=Tiếng Anh
```

Cả `messages_en.properties` và `messages_vi.properties` cố ý **không định nghĩa `page.footer`** để chứng minh một key thiếu bản dịch vẫn được tìm trong `messages.properties`. Ở ví dụ sản phẩm thực, nên có review bản dịch để tránh giao diện trộn ngôn ngữ không chủ đích.

Lưu tệp bằng **UTF-8**, không ghi `\uXXXX` trừ khi bạn đang dùng công cụ đòi hỏi escape riêng. Trong UTF-8, chữ Việt có dấu được giữ nguyên trong Git.

### 6.7. Thymeleaf template

Tệp `src/main/resources/templates/home.html`:

```html
<!doctype html>
<html lang="en"
      xmlns:th="http://www.thymeleaf.org"
      th:lang="${#locale.language}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title th:text="#{page.title}">Welcome</title>
</head>
<body>
  <main>
    <h1 th:text="#{page.title}">Welcome</h1>
    <p th:text="#{page.description}">
      This page uses Spring Boot and MessageSource.
    </p>

    <p th:text="#{greeting.user(${visitorName})}">
      Hello, visitor!
    </p>
    <p th:text="#{items.summary(${itemCount})}">
      You have items.
    </p>
    <p th:text="#{page.footer}">Localization demo</p>

    <nav aria-label="Language">
      <a th:href="@{/(lang='vi')}" th:text="#{language.vi}">
        Tiếng Việt
      </a>
      <a th:href="@{/(lang='en')}" th:text="#{language.en}">
        English
      </a>
    </nav>
  </main>
</body>
</html>
```

Thymeleaf dùng:

- `#{page.title}`: lấy bản dịch từ `MessageSource`.
- `#{greeting.user(${visitorName})}`: lấy message với một tham số.
- `${visitorName}`: lấy biến từ `Model`; **không phải** tra cứu bundle.
- `@{/(lang='vi')}`: tạo URL theo context path, có query `lang=vi`.
- `th:text`: chèn text với escaping HTML; an toàn hơn `th:utext` khi nội dung có thể chứa dữ liệu người dùng.
- `th:lang="${#locale.language}"`: gắn ngôn ngữ tương ứng lên phần tử `<html>` để trình duyệt và công cụ hỗ trợ có thêm ngữ nghĩa.

Template được Thymeleaf tự tìm dưới `classpath:/templates/`. Không cần viết `@ResponseBody` cho handler trả view name `"home"`.

### 6.8. Chạy ứng dụng và xác minh kết quả

Ở thư mục `i18n-demo`, cài JDK 17+ và Maven, chạy:

```bash
mvn spring-boot:run
```

Truy cập `http://localhost:8080/?lang=vi` bằng trình duyệt. Trong một phiên trình duyệt, các phần chính của trang sẽ hiện:

```text
Chào mừng
Trang này dùng Spring Boot và MessageSource.
Xin chào, Lan!
Bạn có 12 sản phẩm.
Localization demo
```

Dòng cuối vẫn tiếng Anh vì `page.footer` chỉ có trong base bundle. Đổi sang `http://localhost:8080/?lang=en` sẽ hiện tiêu đề `Welcome` và câu chào `Hello, Lan!`.

Kiểm tra API **không cần session** bằng header:

```bash
curl -s -H "Accept-Language: vi" \
  "http://localhost:8080/api/greeting?name=Lan"
```

Body chính xác:

```text
Xin chào, Lan!
```

Thử tiếng Anh:

```bash
curl -s -H "Accept-Language: en" \
  "http://localhost:8080/api/greeting?name=Lan"
```

Body chính xác:

```text
Hello, Lan!
```

Các lệnh trên dùng một request mới không gửi cookie session đã chọn locale. Nếu muốn kiểm tra việc **giữ lựa chọn qua session**, dùng cookie jar:

```bash
curl -s -c cookies.txt "http://localhost:8080/?lang=vi" > /dev/null
curl -s -b cookies.txt "http://localhost:8080/api/greeting?name=Lan"
```

Body là `Xin chào, Lan!`. Tệp `cookies.txt` lưu cookie `JSESSIONID` để request sau dùng cùng HTTP session. Nếu server restart mà session không được lưu bền, lựa chọn có thể mất.

Lệnh minh họa dùng shell Bash/Linux/macOS. Trên PowerShell, dùng `curl.exe`, thay nối dòng `\` bằng lệnh trên một dòng; `/dev/null` có thể thay bằng `NUL` hoặc bỏ redirect.

Đóng gói và chạy executable JAR:

```bash
mvn clean package
java -jar target/i18n-demo-1.0.0.jar
```

Cả `templates/home.html` và `i18n/messages*.properties` được đóng gói trong ứng dụng. Trong môi trường có reverse proxy/context path, kiểm tra URL theo triển khai thực tế.

## 7. Tra cứu message trong service, API và validation

### 7.1. Service hoặc controller không dùng template

Khi cần trả nội dung theo locale rõ ràng:

```java
String text = messages.getMessage(
        "greeting.user",
        new Object[] {"Mai"},
        "Hello, Mai!",
        Locale.forLanguageTag("vi-VN")
);
```

Đây là **đoạn mã minh họa bên trong class có biến `messages`**. Với message tiếng Việt trong bundle, chuỗi nhận được là `Xin chào, Mai!`. Nên truyền `Locale` tường minh ở ranh giới API/service, nhất là trong xử lý bất đồng bộ; đừng mặc định mọi thread đều có sẵn request locale.

### 7.2. Thông báo validation

Khi dùng Jakarta Bean Validation với dependency `spring-boot-starter-validation`, thông báo có thể đặt trong `messages.properties` và tra cứu bằng key. Trong một DTO:

```java
@NotBlank(message = "{form.name.required}")
private String name;
```

Các file bundle:

```properties
# messages.properties
form.name.required=Name is required.
```

```properties
# messages_vi.properties
form.name.required=Vui lòng nhập tên.
```

Đây là **đoạn code minh họa**, không phải DTO độc lập. Cần import `jakarta.validation.constraints.NotBlank` và thêm starter validation vào project nếu muốn biên dịch phần này. Spring Boot tích hợp application `MessageSource` vào quá trình resolve các tham số `{...}` của constraint message; sau đó Bean Validation thực hiện interpolation theo cơ chế của nó.

Cũng cần phân biệt **mã lỗi binding** của Spring (`NotBlank.userForm.name`, `typeMismatch...`, ...) với **constraint annotation message template** `{form.name.required}`. `BindingResult` và `MessageCodesResolver` có thể cung cấp nhiều key dự phòng theo thứ tự. Nếu template hiển thị form errors, dùng các expression như `th:errors` để lấy message đã resolve theo locale.

### 7.3. API error response: mã ổn định, message có thể dịch

Một API nên trả mã lỗi ổn định để client xử lý:

```json
{
  "code": "USER_NOT_FOUND",
  "message": "Không tìm thấy người dùng."
}
```

Đây là **ví dụ JSON minh họa**, không phát sinh từ controller ở mục 6. `code` nên độc lập ngôn ngữ; `message` có thể bản địa hóa bằng `MessageSource`. Không dùng chuỗi đã dịch làm điều kiện rẽ nhánh nghiệp vụ hoặc để client so sánh chính xác mã lỗi.

## 8. WebFlux cũng dùng MessageSource, nhưng khác cơ chế lấy locale

Spring WebFlux hỗ trợ i18n và `MessageSource`, nhưng web stack reactive dùng `ServerWebExchange` và `LocaleContextResolver` dành cho WebFlux. Không mang nguyên `LocaleChangeInterceptor`/`SessionLocaleResolver` của Servlet MVC sang một ứng dụng WebFlux.

Trong **WebFlux controller**, có thể lấy locale an toàn từ exchange:

```java
@GetMapping(value = "/reactive-greeting", produces = "text/plain;charset=UTF-8")
public Mono<String> greeting(ServerWebExchange exchange) {
    Locale requested = exchange.getLocaleContext().getLocale();
    Locale locale = requested != null ? requested : Locale.ENGLISH;

    String text = messages.getMessage(
            "greeting.user", new Object[] {"Lan"}, locale);
    return Mono.just(text);
}
```

Đoạn này là **phương thức minh họa, không phải chương trình độc lập**. Nó giả định class có field `MessageSource messages` và imports `Mono`, `ServerWebExchange`, `Locale` cùng các annotation tương ứng. WebFlux thường lấy locale từ `Accept-Language` theo chiến lược HTTP đã cấu hình. Cách đổi ngôn ngữ có lưu trạng thái cần được thiết kế riêng theo WebFlux, session/cookie hoặc tùy biến `LocaleContextResolver` nếu thực sự cần.

**Chú ý khi lập trình reactive:** `LocaleContextHolder` sử dụng ngữ cảnh thread-bound ở nhiều tình huống Servlet, không nên coi nó là nơi chứa locale bảo đảm đúng qua các bước `publishOn`/`subscribeOn` hoặc callbacks bất đồng bộ. Lấy locale từ request/exchange rồi truyền theo dữ liệu hoặc Reactor `Context` khi phù hợp.

Thymeleaf dùng được với cả hai stack khi cấu hình view resolver đúng, nhưng ví dụ hoàn chỉnh mục 6 là **Spring MVC**, nhằm dễ quan sát session-based locale switching.

## 9. Formatting số, ngày, tiền tệ khác với dịch câu chữ

Một lỗi thiết kế phổ biến là đặt tất cả logic format vào bundle:

- `MessageSource` phù hợp cho nhãn, câu thông báo, câu có tham số.
- `NumberFormat`, `DateTimeFormatter`, `@NumberFormat`, `@DateTimeFormat` và Spring `ConversionService` dùng để format dữ liệu theo locale.
- `ZoneId`/time zone xác định vùng thời gian để thể hiện thời điểm chính xác.

Ví dụ Java 17 độc lập (file `LocaleFormattingDemo.java`):

```java
import java.text.NumberFormat;
import java.util.Locale;

public class LocaleFormattingDemo {
    public static void main(String[] args) {
        Locale vi = Locale.forLanguageTag("vi-VN");
        Locale en = Locale.forLanguageTag("en-US");

        System.out.println(NumberFormat.getIntegerInstance(vi).format(12345));
        System.out.println(NumberFormat.getIntegerInstance(en).format(12345));
    }
}
```

Chạy:

```bash
javac LocaleFormattingDemo.java
java LocaleFormattingDemo
```

Trong JDK sử dụng dữ liệu locale CLDR thông thường, stdout:

```text
12.345
12,345
```

Dữ liệu locale provider/JDK có thể ảnh hưởng cách format trong môi trường đặc biệt; với test quan trọng, hãy cố định JDK và locale provider. Ví dụ này cho thấy **cùng số 12345** nhưng ký tự phân tách hàng nghìn tùy ngôn ngữ/vùng.

Với giá tiền, **locale format không tự chọn đúng đơn vị tiền tệ nghiệp vụ**. Nếu người dùng chọn tiếng Việt nhưng thanh toán USD, giữ mã tiền tệ là USD và dùng định dạng theo chính sách sản phẩm; không suy đoán đơn vị tiền tệ chỉ từ locale.

## 10. Kiến trúc và quy ước bản dịch cho dự án thật

### 10.1. Thiết kế khóa có ngữ cảnh

Nên dùng key ổn định, dễ tìm:

```properties
nav.home=Home
auth.login.title=Sign in
auth.login.button=Continue
auth.error.invalid-credentials=Incorrect username or password.
order.summary.total=Total
order.error.not-found=Order was not found.
```

Không nên lạm dụng key như `text1`, `text2` hoặc dùng nguyên câu tiếng Anh làm key, vì khi copy thay đổi sẽ khó kiểm soát. Nên nhóm key theo màn hình/domain hoặc module. Các nhóm khác nhau vẫn có thể dùng nhiều basename như `i18n/messages,i18n/errors`.

### 10.2. Một mã lỗi, nhiều cách hiển thị

Service nên tạo **mã lỗi + dữ liệu**, để lớp web chọn locale và render message. Ví dụ service phát `ORDER_NOT_FOUND` với ID, controller ánh xạ sang key `order.error.not-found` và các args tương ứng. Điều này giữ logic nghiệp vụ không phụ thuộc ngôn ngữ hiện hành.

### 10.3. Không ghép câu bằng nhiều mảnh nhỏ

Tránh:

```java
String message = labelBefore + quantity + labelAfter;
```

Trật tự từ có thể khác nhau giữa ngôn ngữ. Tốt hơn là đặt **cả câu** trong bundle, ví dụ `items.summary=You have {0} items` và `items.summary=Bạn có {0} sản phẩm`. Dịch giả có thể đảo vị trí tham số mà không phải đổi code.

Với plural/gender phức tạp, `MessageFormat` chuẩn và message bundles đơn giản có giới hạn. Có thể cần pluralization logic chuyên dụng hoặc ICU MessageFormat; đừng kỳ vọng một mẫu `{0}` tự xử lý tất cả số ít/số nhiều của mọi ngôn ngữ. Ví dụ `You have 1 items` là câu sai ngữ pháp nếu không có nhánh số ít.

### 10.4. Giao diện, HTML và accessibility

- Dùng `th:text` để escape HTML khi in bản dịch có dữ liệu người dùng. Chỉ dùng `th:utext` với HTML đã được kiểm duyệt và xử lý an toàn.
- Đặt `lang` trên phần tử HTML tương ứng, quan tâm `dir="rtl"` khi hỗ trợ ngôn ngữ viết từ phải sang trái.
- Kiểm thử text dài hơn, xuống dòng, nút chật, screen reader và keyboard navigation; bản dịch không chỉ là thay giá trị key.
- Tránh xem `Accept-Language` là dữ liệu định danh. Thay đổi ngôn ngữ là tùy chọn UI, không cho phép nâng quyền.

### 10.5. Cache, phân phối và session

Một trang HTML trả nội dung khác nhau tùy `Accept-Language` hoặc cookie/session. Nếu reverse proxy/CDN cache response, cần chính sách cache phù hợp; nếu chọn ngôn ngữ theo header và response cache được, hãy cân nhắc `Vary: Accept-Language`. Nếu chọn bằng session/cookie, tránh shared cache vô tình phát HTML ngôn ngữ của người này cho người khác.

Với `SessionLocaleResolver`, nhiều instance backend cần cùng chính sách session hoặc session store phù hợp khi muốn lựa chọn ngôn ngữ tồn tại qua nhiều máy chủ. Nếu muốn frontend/API stateless, header `Accept-Language` thường đơn giản hơn session locale.

## 11. Các lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| Không có bản dịch dù đã tạo `messages_vi.properties` | Thiếu `messages.properties` nên Boot không auto-configure, hoặc basename sai | Tạo base bundle; kiểm tra `spring.messages.basename` và classpath |
| Hiện key `page.title` hoặc marker lỗi thay vì câu | Key không tồn tại hoặc bundle không được tìm thấy | Kiểm tra chính tả, package, thư mục và fallback |
| Tiếng Việt bị lỗi dấu | File không thực sự UTF-8 hoặc response charset không đúng | Xác nhận editor, `spring.messages.encoding` và HTTP response encoding |
| Click `?lang=vi` nhưng ngôn ngữ không đổi | Vẫn dùng `AcceptHeaderLocaleResolver` hoặc interceptor chưa đăng ký | Dùng `SessionLocaleResolver`/`CookieLocaleResolver` và `LocaleChangeInterceptor` phù hợp |
| Đổi ngôn ngữ một lần nhưng request sau quay lại ban đầu | Client không gửi cookie/session cũ hoặc session đã hết | Kiểm tra `JSESSIONID`, session store và cách request được thực hiện |
| Header `Accept-Language: vi` không có tác dụng | Session đã lưu locale khác và có ưu tiên cao hơn | Thử session mới/không cookie; kiểm tra resolver đang dùng |
| Câu với `{0}` hiển thị nguyên dạng | Không truyền args đúng hoặc pattern không được format như mong đợi | Kiểm tra `MessageSource.getMessage`, placeholder và cấu hình `MessageFormat` |
| Dấu `'` mất/biến dạng | Quy tắc escape của `MessageFormat` | Dùng `''` khi cần trong message được format, test với args |
| Đổi locale nhưng thời gian vẫn sai múi giờ | Locale không tự đổi `ZoneId` | Chọn time zone riêng rồi format ngày/giờ |
| Thymeleaf không tìm `home` | Sai vị trí `templates/home.html` hoặc thiếu starter Thymeleaf | Kiểm tra dependency, return view name, template path |
| Bản dịch đúng trong Java nhưng sai trên trang | Template dùng literal text hoặc sai expression | Dùng `th:text="#{...}"`, kiểm tra request locale |
| API bị trả HTML lỗi từ validation | Lớp render lỗi chưa dùng cùng MessageSource/locale | Chuẩn hóa error code, message resolution và response type |
| Chỉ có tiếng Anh ở production | Resource bundles không vào executable JAR | Kiểm tra `jar tf`, build resource filtering, profile và đóng gói |
| Cache CDN phát nhầm ngôn ngữ | Không tách cache key theo locale hoặc cache nhầm HTML cá nhân hóa | Chỉnh cache control, `Vary` và cookie/session policy |

### Quy trình chẩn đoán có thứ tự

1. Xác nhận **locale thực tế** của request bằng log hoặc controller tạm thời; đừng chỉ nhìn ngôn ngữ hệ điều hành.
2. Xác nhận source của locale: `Accept-Language`, session, cookie hay resolver tùy chỉnh.
3. Kiểm tra **basename và file bundle thực tế trên classpath** bằng cấu trúc project/executable JAR.
4. Kiểm tra key trong base và bản dịch, rồi thử `messages.getMessage(code, args, default, locale)` với locale tường minh.
5. Kiểm tra Thymeleaf expression, encoding HTML/HTTP và caching; nếu text có args, kiểm tra escaping `MessageFormat`.
6. Khi mọi thứ chạy trong IDE nhưng lỗi trên production, kiểm tra packaging, session/reverse proxy và các request headers/cookies.

Đừng “chữa cháy” bằng cách viết hàng loạt `if (locale.getLanguage().equals("vi"))` trong controller: cách này bỏ qua fallback, làm rối logic giao diện và khiến quản lý bản dịch khó mở rộng.

## 12. Kiểm thử bản địa hóa có hệ thống

### 12.1. Ma trận case cơ bản

| Case | Đầu vào | Điều cần xác minh |
| --- | --- | --- |
| Tiếng Việt qua header | `Accept-Language: vi`, session mới | `greeting.user` là “Xin chào, Lan!” |
| Tiếng Anh qua header | `Accept-Language: en` | `greeting.user` là “Hello, Lan!” |
| Tiếng Anh vùng cụ thể | `Accept-Language: en-GB` | Dùng `messages_en_GB` nếu có, sau đó fallback |
| Locale chưa hỗ trợ | `Accept-Language: fr-FR` | Fallback về base có kiểm soát, không 500 |
| Thiếu key ở file vi | `page.footer` với locale vi | Nhận `Localization demo` từ base |
| Không có key ở tất cả bundle | `missing.key` | Dùng default hoặc `NoSuchMessageException` tùy overload |
| Query thay ngôn ngữ | `/?lang=vi` rồi request cùng cookie | Session giữ lựa chọn |
| Request mới không cookie | Header mới hoặc locale mặc định | Không vô tình giữ locale của người trước |
| Tham số có ký tự đặc biệt | Tên `<Lan>` trong model | HTML được escape bởi `th:text` |
| Chữ tiếng Việt và số | Dấu tiếng Việt, `{0,number,integer}` | Render UTF-8 và format đúng locale |

### 12.2. Kiểm tra bằng `curl`

Chạy server rồi thử hai request với ngôn ngữ khác nhau:

```bash
curl -i -H "Accept-Language: vi" \
  "http://localhost:8080/api/greeting?name=Lan"

curl -i -H "Accept-Language: en" \
  "http://localhost:8080/api/greeting?name=Lan"
```

`-i` in HTTP headers kèm body; quan sát `Content-Type` với charset và body tiếng Việt. Khi kiểm thử trạng thái session, dùng `-c`/`-b` như mục 6.8 thay vì gọi mỗi request rời rạc rồi kết luận session không hoạt động.

Trong unit test cho message bundle, có thể inject `MessageSource` và gọi với `Locale.forLanguageTag("vi")` trực tiếp để loại trừ yếu tố HTTP/session. Trong integration test, tạo các request có header và cookie khác nhau; nên kiểm thử cả missing key, fallback và lỗi encoding.

### 12.3. Kiểm soát chất lượng bản dịch

- Kiểm tra key bị thiếu hoặc chỉ có ở một ngôn ngữ trong CI; một số key cố ý fallback, cần được ghi nhận.
- Bảo đảm placeholder của cùng một key tương thích giữa các ngôn ngữ: `{0}`, `{1}` và kiểu định dạng.
- Không để UI dùng nhiều từ chưa dịch mà không chủ đích.
- Kiểm tra locale chịu ảnh hưởng từ browser, session, reverse proxy và cache.
- Kiểm thử giao diện ở màn hình nhỏ, chuỗi dài, RTL và hỗ trợ tiếp cận.

## 13. Các câu hỏi tự đánh giá

1. **`MessageSource` và `LocaleResolver` có cùng nhiệm vụ không?** Không. Resolver chọn locale của request; MessageSource dùng locale đó để tìm thông điệp.
2. **Chỉ có `messages_vi.properties`, không có `messages.properties`, Boot có chắc tạo MessageSource tự động không?** Không. Auto-configuration cần base bundle cho basename tương ứng.
3. **`messages_vi_VN.properties` khác `messages_vi.properties` như thế nào?** Bản đầu cụ thể hơn theo quốc gia; bản sau dành chung cho tiếng Việt.
4. **Tại sao `?lang=vi` không hoạt động với `AcceptHeaderLocaleResolver`?** Resolver đó không hỗ trợ `setLocale`; phải chọn cơ chế có thể đổi trạng thái như session/cookie.
5. **`getMessage(code,args,locale)` và `getMessage(code,args,default,locale)` khác nhau ở đâu?** Bản có default trả text dự phòng khi thiếu key; bản không default có thể ném `NoSuchMessageException`.
6. **`{0}` trong file message là cú pháp gì?** Placeholder của `java.text.MessageFormat`; không phải `${...}` của Thymeleaf.
7. **Chọn `vi-VN` có tự biết múi giờ của người dùng không?** Không. Cần xử lý `ZoneId`/time zone riêng.
8. **Vì sao không nên dùng chuỗi dịch làm mã lỗi API?** Bản dịch thay đổi theo locale và có thể cập nhật; code máy đọc cần ổn định.
9. **Có thể dùng MessageSource trong WebFlux không?** Có, nhưng cần lấy request locale theo cơ chế WebFlux, ví dụ qua `ServerWebExchange`.
10. **Nếu HTML server render theo header, cache cần chú ý gì?** Phải tránh trộn response của các locale/người dùng, cân nhắc `Vary: Accept-Language` và cache policy phù hợp.

## 14. Tài liệu chính thức và hướng đọc tiếp

- Spring Boot — [Internationalization](https://docs.spring.io/spring-boot/reference/features/internationalization.html): auto-configuration, base bundle, basename và fallback.
- Spring Boot 3.5 — [Common application properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.messages.*`.
- Spring Framework — [`ApplicationContext` và `MessageSource`](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): API, ResourceBundle, exception và fallback.
- Spring Framework — [Spring MVC Locale Resolver và LocaleChangeInterceptor](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/localeresolver.html): Accept-Language, session, cookie, chuyển ngôn ngữ.
- Spring Boot — [Validation](https://docs.spring.io/spring-boot/reference/io/validation.html): sử dụng messages khi resolve Bean Validation.
- Thymeleaf — [Tutorial: Thymeleaf + Spring](https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html): Spring `MessageSource` và template expressions.
- Thymeleaf — [Using Thymeleaf](https://www.thymeleaf.org/doc/tutorials/3.1/usingthymeleaf.html): `#{...}`, `${...}`, `@{...}` và tham số message.
- Spring Framework — [WebFlux configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): locale/formatting và khác biệt với MVC.

**Ghi nhớ:** `LocaleResolver` (hoặc WebFlux locale context) trả lời **“request đang dùng locale nào?”**; `MessageSource` trả lời **“key này dịch thành câu gì trong locale ấy?”**; Thymeleaf/Controller quyết định **“thông điệp đó hiển thị ở đâu?”**. Giữ các trách nhiệm tách biệt giúp giao diện Spring Boot mở rộng ngôn ngữ, kiểm thử và bảo trì dễ dàng.