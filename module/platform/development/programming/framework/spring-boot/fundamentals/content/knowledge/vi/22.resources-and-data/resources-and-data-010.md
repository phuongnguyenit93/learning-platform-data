# MessageSource, thông báo lỗi và lựa chọn ngôn ngữ

Một ứng dụng Spring Boot có thể được sử dụng bởi người dùng Việt Nam, người dùng nói tiếng Anh hoặc khách hàng ở nhiều quốc gia khác nhau. Nếu thông báo được viết trực tiếp trong service, controller và validation annotation, ứng dụng sẽ nhanh chóng gặp khó khăn khi cần đổi ngôn ngữ, sửa câu chữ hoặc bổ sung bản dịch.

Ví dụ, cùng một lỗi nghiệp vụ “không tìm thấy người dùng” nên có thể được trình bày khác nhau:

~~~text
Ngôn ngữ Việt: Không tìm thấy người dùng có mã 42.
English:        User with ID 42 was not found.
~~~

Trong khi đó, **mã lỗi nghiệp vụ** vẫn nên giữ nguyên, chẳng hạn `USER_NOT_FOUND`. Mã lỗi giúp hệ thống, log và client phân biệt trường hợp lỗi; **thông điệp được dịch** giúp con người hiểu và xử lý.

Spring Framework cung cấp **`MessageSource`** để giải quyết thông điệp theo mã, tham số và `Locale`. Spring Boot hỗ trợ tự động cấu hình nguồn thông điệp từ các file `messages*.properties`. Khi kết hợp với Spring MVC và Bean Validation, cơ chế này hỗ trợ thông báo lỗi đa ngôn ngữ mà không cần viết nhánh `if/else` cho từng ngôn ngữ trong logic nghiệp vụ.

Bài học thuộc **Spring Boot Fundamentals → Tài nguyên và dữ liệu**, tập trung vào các vấn đề thực hành:

- MessageSource hoạt động như thế nào?
- Đặt file thông điệp ở đâu và chọn khóa (message code) thế nào?
- Locale được xác định từ `Accept-Language`, tham số hay lựa chọn của người dùng ra sao?
- Chuyển một exception hoặc lỗi `@Valid` thành phản hồi API theo ngôn ngữ mong muốn thế nào?
- Xử lý thiếu bản dịch, placeholder, mã hóa UTF-8, caching và kiểm thử ra sao?
- Làm thế nào để việc dịch thông báo không gây phụ thuộc ngược vào logic nghiệp vụ?

## 1. Ba khái niệm cốt lõi: message code, arguments và Locale

Một thông điệp đa ngôn ngữ thường có ba thành phần.

**Message code** là khóa ổn định biểu diễn ý nghĩa, ví dụ:

~~~text
error.user.not-found
error.request.invalid
validation.user.email.invalid
notification.order.created
~~~

**Arguments** là những dữ liệu động cần chèn vào câu, ví dụ ID người dùng, số lượng hoặc tên đối tượng.

**Locale** mô tả quy ước ngôn ngữ và vùng, ví dụ:

~~~text
vi        Tiếng Việt
vi-VN     Tiếng Việt tại Việt Nam
en        Tiếng Anh
en-US     Tiếng Anh tại Hoa Kỳ
en-GB     Tiếng Anh tại Vương quốc Anh
~~~

Spring kết hợp các thông tin đó:

~~~text
Message code: error.user.not-found
Arguments:    [42]
Locale:       vi-VN
               |
               v
          MessageSource
               |
               v
"Không tìm thấy người dùng có mã 42."
~~~

Cùng code và arguments, nhưng với `en-US`:

~~~text
"User with ID 42 was not found."
~~~

Vì vậy, service chỉ cần quyết định **điều gì đã xảy ra**, còn lớp trình bày thông báo quyết định **nói điều đó bằng ngôn ngữ nào**.

## 2. MessageSource là gì?

`MessageSource` là interface của Spring Framework trong package:

~~~java
org.springframework.context.MessageSource
~~~

Các phương thức quan trọng:

~~~java
String getMessage(
        String code,
        Object[] args,
        String defaultMessage,
        Locale locale
);

String getMessage(
        String code,
        Object[] args,
        Locale locale
) throws NoSuchMessageException;

String getMessage(
        MessageSourceResolvable resolvable,
        Locale locale
) throws NoSuchMessageException;
~~~

Ý nghĩa:

| Tham số hoặc kiểu | Vai trò |
|---|---|
| `code` | Khóa tra cứu thông điệp |
| `args` | Dữ liệu thay cho các placeholder như `{0}`, `{1}` |
| `defaultMessage` | Câu dự phòng khi không tìm thấy code |
| `locale` | Ngôn ngữ/vùng dùng để tra bản dịch |
| `MessageSourceResolvable` | Đối tượng chứa một hoặc nhiều code, arguments và thông điệp mặc định |
| `NoSuchMessageException` | Lỗi khi không tìm thấy message và không có fallback hợp lệ |

Ví dụ sử dụng:

~~~java
String message = messageSource.getMessage(
        "error.user.not-found",
        new Object[] {42L},
        Locale.forLanguageTag("vi-VN")
);
~~~

Nếu bundle có khai báo phù hợp, kết quả sẽ là:

~~~text
Không tìm thấy người dùng có mã 42.
~~~

### MessageSource không phải kho lưu dữ liệu nghiệp vụ

`MessageSource` không thay thế database, object storage hay hệ thống lưu trữ file chung. Nó được thiết kế để **phân giải thông điệp theo mã và locale**, thường từ các resource bundle.

Ví dụ:

- “Không tìm thấy người dùng” là message phù hợp.
- “Tên người dùng không được để trống” là message phù hợp.
- Một bảng giá hàng triệu dòng không phải dữ liệu nên đưa vào message bundle.
- Một file JSON lớn chứa toàn bộ catalog sản phẩm cũng không nên coi như resource bundle dịch thông báo.

Một ứng dụng có thể dùng cả `ResourceLoader` để đọc dữ liệu và `MessageSource` để dịch văn bản. Hai abstraction phục vụ những mục đích riêng.

## 3. Cấu hình tối thiểu trong Spring Boot

Trong một ứng dụng Spring Boot thông thường, hãy tạo các file dưới `src/main/resources`:

~~~text
src/
  main/
    java/
      com/example/DemoApplication.java
    resources/
      application.properties
      messages.properties
      messages_vi.properties
      messages_vi_VN.properties
~~~

File gốc `messages.properties`:

~~~properties
error.user.not-found=User with ID {0} was not found.
error.request.invalid=The request contains invalid data.
error.common.unexpected=An unexpected error occurred.
validation.user.name.required=User name is required.
validation.user.email.required=Email is required.
validation.user.email.invalid=Email address is invalid.
notification.order.created=Order {0} was created successfully.
~~~

File `messages_vi.properties`:

~~~properties
error.user.not-found=Không tìm thấy người dùng có mã {0}.
error.request.invalid=Dữ liệu yêu cầu không hợp lệ.
error.common.unexpected=Đã xảy ra lỗi không mong muốn.
validation.user.name.required=Tên người dùng không được để trống.
validation.user.email.required=Email không được để trống.
validation.user.email.invalid=Địa chỉ email không hợp lệ.
notification.order.created=Đã tạo đơn hàng {0} thành công.
~~~

File `messages_vi_VN.properties` là tùy chọn, dùng khi cần bản dịch riêng cho khu vực Việt Nam:

~~~properties
notification.order.created=Đơn hàng số {0} đã được tạo thành công.
~~~

Nếu không cần phân biệt `vi` và `vi-VN`, hoàn toàn có thể chỉ dùng `messages_vi.properties`.

### Tại sao phải có messages.properties?

Với cơ chế tự động cấu hình nguồn thông điệp từ bundle mặc định của Spring Boot, **file gốc `messages.properties` cần hiện diện** để việc phát hiện bundle mặc định hoạt động như mong đợi. Chỉ tạo file `messages_vi.properties` mà không có file cơ sở có thể khiến auto-configuration không tạo bean message source như bạn dự tính.

Khi đã có bundle phù hợp, Spring Boot có thể cung cấp `MessageSource` để inject vào các bean ứng dụng mà không cần tự viết `@Bean`.

Nếu dự án sử dụng một basename khác, tương tự cần tạo bundle gốc tương ứng, ví dụ `i18n/messages.properties`.

### Cấu hình mặc định và tường minh

Trong `application.properties` có thể viết:

~~~properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
~~~

Ý nghĩa:

- `spring.messages.basename=messages`: bundle cơ sở là `messages`, không ghi đuôi `.properties`.
- `spring.messages.encoding=UTF-8`: chỉ rõ encoding để đọc tài nguyên thông điệp.
- `spring.messages.fallback-to-system-locale=false`: tránh phụ thuộc ngôn ngữ mặc định của máy chủ khi chọn fallback.

Các phiên bản Spring Boot hiện đại đã có những giá trị mặc định thích hợp cho một số property trên. Việc khai báo tường minh giúp người học nhìn rõ cấu hình đang được sử dụng.

## 4. Spring chọn file thông điệp theo Locale như thế nào?

Giả sử yêu cầu hiện tại có locale `vi-VN` và ứng dụng có ba file:

~~~text
messages_vi_VN.properties
messages_vi.properties
messages.properties
~~~

Khi giải quyết một code, Spring có thể tìm giá trị phù hợp theo mức độ cụ thể của locale rồi fallback về bundle cơ sở.

Ví dụ code `notification.order.created` tồn tại trong `messages_vi_VN.properties` nên câu phù hợp sẽ là:

~~~text
Đơn hàng số 108 đã được tạo thành công.
~~~

Với code `error.user.not-found` không có trong `messages_vi_VN.properties` nhưng có trong `messages_vi.properties`, nó có thể dùng câu:

~~~text
Không tìm thấy người dùng có mã 42.
~~~

Nếu không có bản dịch phù hợp ở file tiếng Việt, bundle cơ sở có thể được dùng.

Sơ đồ minh họa:

~~~text
Locale vi-VN, code error.user.not-found
                |
                v
messages_vi_VN.properties
     Không có code
                |
                v
messages_vi.properties
     Có code
                |
                v
"Không tìm thấy người dùng có mã 42."
~~~

Tập fallback thực tế còn chịu ảnh hưởng của configuration như `fallback-to-system-locale`, default locale hoặc cách bean `MessageSource` được cấu hình thủ công.

### Bundle cơ sở nên có ý nghĩa rõ ràng

Nếu quyết định `messages.properties` là tiếng Anh mặc định, hãy giữ quy ước đó nhất quán. Điều này giúp ứng dụng vẫn có câu dễ hiểu khi một bản dịch mới chưa được cập nhật.

Nếu sản phẩm ưu tiên tiếng Việt, có thể chọn tiếng Việt làm nội dung base; tuy nhiên phải xác định rõ chính sách fallback và locale mặc định của sản phẩm. **Tên file gốc không tự nói rằng nội dung của nó phải là tiếng Anh.**

## 5. Chèn tham số bằng MessageFormat

Trong message bundle, `{0}`, `{1}`... là những placeholder dành cho arguments.

Ví dụ:

~~~properties
error.order.not-allowed=Cannot process order {0} in status {1}.
~~~

Gọi:

~~~java
String message = messageSource.getMessage(
        "error.order.not-allowed",
        new Object[] {1507L, "CANCELLED"},
        Locale.ENGLISH
);
~~~

Kết quả:

~~~text
Cannot process order 1,507 in status CANCELLED.
~~~

Lưu ý: với `MessageFormat`, cách hiển thị số có thể phụ thuộc locale; ví dụ trên minh họa dấu phân tách hàng nghìn ở tiếng Anh. Nếu mã định danh phải giữ nguyên từng chữ số, hãy cân nhắc truyền dạng String thay cho một số cần format.

### Đừng nối câu bằng cách ghép các mảnh đã dịch

Tránh:

~~~java
String message =
        messageSource.getMessage("error.prefix", null, locale)
        + userId
        + messageSource.getMessage("error.suffix", null, locale);
~~~

Cách này giả định mọi ngôn ngữ đều có cùng trật tự từ. Dịch giả có thể cần đặt mã hoặc tên đối tượng ở một vị trí khác.

Tốt hơn:

~~~properties
# messages.properties
error.user.not-found=User with ID {0} was not found.
~~~

~~~properties
# messages_vi.properties
error.user.not-found=Không tìm thấy người dùng có mã {0}.
~~~

Thứ tự của `{0}` trong từng câu do bản dịch quyết định.

### Dấu nháy đơn trong MessageFormat

Cú pháp `MessageFormat` dùng dấu nháy đơn để quote ký tự đặc biệt. Vì vậy, những câu có placeholder cần đặc biệt lưu ý dấu `'`.

Ví dụ dùng dấu nháy đơn quanh mã:

~~~properties
error.code.invalid=Code ''{0}'' is invalid.
~~~

Khi được xử lý bởi `MessageFormat`, cặp `''` giúp hiển thị một dấu nháy đơn. Nếu viết `'{0}'`, placeholder có thể bị coi là văn bản literal thay vì được thay bằng argument.

Hãy kiểm thử những thông điệp có dấu nháy, ngoặc nhọn, số và ngày tháng. Không nên tự dùng `String.replace(...)` thay cho MessageFormat nếu cần i18n thực sự.

## 6. Tiêm MessageSource vào service

Trong Spring Boot, cách sử dụng phổ biến là constructor injection:

~~~java
package com.example.i18n;

import java.util.Locale;

import org.springframework.context.MessageSource;
import org.springframework.stereotype.Service;

@Service
public class LocalizedMessageService {

    private final MessageSource messageSource;

    public LocalizedMessageService(MessageSource messageSource) {
        this.messageSource = messageSource;
    }

    public String userNotFound(long userId, Locale locale) {
        return messageSource.getMessage(
                "error.user.not-found",
                new Object[] {userId},
                locale
        );
    }

    public String orderCreated(long orderId, Locale locale) {
        return messageSource.getMessage(
                "notification.order.created",
                new Object[] {orderId},
                locale
        );
    }
}
~~~

Service không phải tự chọn file `messages_vi.properties` hoặc `messages.properties`. Nó chỉ cần code, arguments và locale.

### Vì sao truyền Locale vào method?

Truyền `Locale` tường minh giúp người đọc hiểu câu trả lời phụ thuộc vào ngôn ngữ nào. Điều này đặc biệt hữu ích với:

- Background worker không gắn với HTTP request.
- Email được gửi sau khi một request đã kết thúc.
- Scheduled job tạo thông báo cho nhiều tài khoản.
- Test muốn chọn locale cố định.
- Một hành động gửi thông báo tới người nhận có ngôn ngữ khác với người khởi tạo hành động.

Trong service nghiệp vụ sâu bên dưới, không nên phụ thuộc vào header HTTP một cách mặc định. Lớp ứng dụng có thể truyền `Locale` hoặc preference đã được xác minh xuống lớp trình bày thông báo.

## 7. Locale là gì, và nó không phải cái gì?

`java.util.Locale` chứa thông tin như language và country/region, thường tạo bằng:

~~~java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale englishUS = Locale.forLanguageTag("en-US");
Locale englishUK = Locale.forLanguageTag("en-GB");
~~~

Có thể đọc:

~~~java
System.out.println(vietnamese.getLanguage()); // vi
System.out.println(vietnamese.getCountry());  // VN
~~~

`Locale` có thể ảnh hưởng:

- Ngôn ngữ của câu trong MessageSource.
- Cách format số và ngày tháng.
- Quy ước vùng cho tiền tệ hoặc định dạng trình bày.
- Cách lấy bundle cụ thể như `messages_vi_VN.properties`.

**Locale không phải múi giờ.** Người nói tiếng Việt có thể đang ở châu Âu; người dùng đặt ngôn ngữ tiếng Anh có thể muốn múi giờ Việt Nam. Trong ứng dụng thực tế, language, region, time zone và currency preference là những khái niệm khác nhau, dù đôi khi được thiết lập cùng lúc.

**Locale cũng không phải quyền truy cập.** Không được dùng `Accept-Language` hay tên bundle để quyết định authorization hoặc dữ liệu nào được phép truy cập.

## 8. Spring MVC lấy Locale từ đâu?

Trong ứng dụng Spring MVC, một `LocaleResolver` quyết định locale của request. Với cấu hình MVC thông thường, nếu không tự cung cấp resolver, Spring sử dụng cách giải quyết locale dựa trên header `Accept-Language`.

Ví dụ HTTP:

~~~http
GET /api/users/42 HTTP/1.1
Host: localhost:8080
Accept-Language: vi-VN,vi;q=0.9,en;q=0.8
~~~

Header này mô tả thứ tự ưu tiên ngôn ngữ từ client:

- `vi-VN` ưu tiên cao.
- `vi` ưu tiên tiếp theo.
- `en` có thể dùng khi cần fallback.

Trong controller Spring MVC, ta có thể nhận `Locale` trực tiếp như một tham số:

~~~java
@GetMapping("/greeting")
public String greeting(Locale locale) {
    return messageSource.getMessage(
            "greeting.hello",
            null,
            locale
    );
}
~~~

Thêm key:

~~~properties
# messages.properties
greeting.hello=Hello!
~~~

~~~properties
# messages_vi.properties
greeting.hello=Xin chào!
~~~

Ví dụ gọi:

~~~bash
curl -H "Accept-Language: vi-VN" \
     http://localhost:8080/greeting
~~~

Kết quả mong đợi:

~~~text
Xin chào!
~~~

Nếu gửi:

~~~bash
curl -H "Accept-Language: en-US" \
     http://localhost:8080/greeting
~~~

Kết quả thường là:

~~~text
Hello!
~~~

Cần nhớ rằng **`Locale` được Spring MVC giải quyết từ request**, chứ không phải controller tự parse header trong những ví dụ trên.

### Vì sao không đọc header bằng String thủ công?

Đoạn sau chỉ lấy raw header:

~~~java
@RequestHeader("Accept-Language") String rawHeader
~~~

Header có thể chứa nhiều language ranges và hệ số quality `q`. Tự tách chuỗi theo dấu phẩy rồi lấy phần đầu không phản ánh đầy đủ những quy tắc giải quyết locale, locale được hỗ trợ hoặc fallback của ứng dụng.

Sử dụng `Locale` parameter với resolver phù hợp thường đơn giản và nhất quán hơn.

## 9. AcceptHeaderLocaleResolver và ứng dụng stateless

`AcceptHeaderLocaleResolver` dùng thông tin từ `Accept-Language` để xác định locale. Nó phù hợp cho API stateless khi client chủ động gửi ngôn ngữ mong muốn theo từng request.

Luồng điển hình:

~~~text
Mobile App / Browser
    |
    | Accept-Language: vi-VN
    v
Spring MVC
    |
    v
LocaleResolver -> Locale vi-VN
    |
    v
Controller / ExceptionHandler
    |
    v
MessageSource
    |
    v
HTTP response có message tiếng Việt
~~~

Ưu điểm:

- Không cần lưu trạng thái ngôn ngữ trong server session.
- Mỗi request có thể yêu cầu một ngôn ngữ.
- Phù hợp khi các client khác nhau gọi chung một backend.

Giới hạn:

- Header là một **ưu tiên do client cung cấp**, không phải thông tin danh tính đã xác thực.
- Nếu ứng dụng chỉ hỗ trợ vài ngôn ngữ, cần quy định supported locales và fallback.
- Nếu người dùng đã chọn ngôn ngữ trong tài khoản, quy tắc chọn ngôn ngữ cần cân bằng giữa preference được lưu và header của từng request.

### Chọn danh sách locale hỗ trợ

Ví dụ cấu hình resolver tường minh:

~~~java
package com.example.i18n;

import java.util.List;
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.LocaleResolver;
import org.springframework.web.servlet.i18n.AcceptHeaderLocaleResolver;

@Configuration(proxyBeanMethods = false)
public class LocaleConfiguration {

    @Bean
    LocaleResolver localeResolver() {
        AcceptHeaderLocaleResolver resolver =
                new AcceptHeaderLocaleResolver();

        resolver.setSupportedLocales(List.of(
                Locale.forLanguageTag("vi-VN"),
                Locale.forLanguageTag("en-US")
        ));

        resolver.setDefaultLocale(Locale.forLanguageTag("vi-VN"));
        return resolver;
    }
}
~~~

`setSupportedLocales(...)` giúp giới hạn những locale mà ứng dụng mong muốn hỗ trợ, và `setDefaultLocale(...)` cung cấp fallback.

**Lưu ý:** logic match language và country của resolver cần được hiểu đúng. Nếu danh sách hỗ trợ chỉ có `en-US`, không nên mặc định mọi yêu cầu `en-GB` sẽ được xử lý như `en-US` theo quy tắc khớp vùng mà bạn tự suy đoán. Hãy kiểm thử các language tags mà sản phẩm thực sự cho phép.

### Có thể đổi ngôn ngữ bằng ?lang=vi cho AcceptHeaderLocaleResolver không?

Không nên kỳ vọng điều đó. `AcceptHeaderLocaleResolver` dùng header của request; nó không được thiết kế để thay đổi locale lưu trên server bằng lời gọi `setLocale(...)`.

Nếu bạn muốn người dùng đổi ngôn ngữ bằng query parameter và ghi nhớ lựa chọn cho các request tiếp theo, hãy dùng resolver hỗ trợ trạng thái như session hoặc cookie, hoặc thiết kế cơ chế preference riêng. Tránh ghép `LocaleChangeInterceptor` với một resolver không hỗ trợ thay đổi locale rồi giả định nó hoạt động.

## 10. Lựa chọn ngôn ngữ bằng tham số, session hoặc cookie

Một website render HTML có thể cho người dùng chọn ngôn ngữ từ giao diện:

~~~text
https://example.org/home?lang=vi-VN
https://example.org/home?lang=en-US
~~~

Với Spring MVC, có thể dùng `SessionLocaleResolver` và `LocaleChangeInterceptor`.

Ví dụ cấu hình:

~~~java
package com.example.i18n;

import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.LocaleResolver;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.i18n.LocaleChangeInterceptor;
import org.springframework.web.servlet.i18n.SessionLocaleResolver;

@Configuration(proxyBeanMethods = false)
public class LanguageSelectionConfiguration
        implements WebMvcConfigurer {

    @Bean
    LocaleResolver localeResolver() {
        SessionLocaleResolver resolver = new SessionLocaleResolver();
        resolver.setDefaultLocale(Locale.forLanguageTag("vi-VN"));
        return resolver;
    }

    @Bean
    LocaleChangeInterceptor localeChangeInterceptor() {
        LocaleChangeInterceptor interceptor =
                new LocaleChangeInterceptor();
        interceptor.setParamName("lang");
        return interceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(localeChangeInterceptor());
    }
}
~~~

Cách hoạt động:

1. Request có `?lang=en-US`.
2. Interceptor đọc tham số `lang`.
3. `SessionLocaleResolver` lưu locale lựa chọn trong HTTP session.
4. Những request sau thuộc session đó có thể tiếp tục dùng locale đã chọn.
5. MessageSource lấy bản dịch tương ứng.

Đây là **một lựa chọn thay thế** cho resolver dùng `Accept-Language` ở mục 9. Không nên đồng thời khai báo hai bean `LocaleResolver` trùng tên trong cùng ứng dụng rồi kỳ vọng Spring tự biết resolver nào phải dùng.

### Session và cookie có phù hợp với mọi API không?

Không nhất thiết. API stateless thường ưu tiên header, explicit locale parameter hoặc preference lấy từ hồ sơ người dùng đã xác thực. Website truyền thống có session hoặc cookie có thể hợp với `SessionLocaleResolver` hoặc `CookieLocaleResolver` hơn.

Nếu dùng cookie, cần cân nhắc thời hạn, domain, bảo vệ cookie và cách xử lý khi người dùng chưa đăng nhập. Nếu dùng session, cần cân nhắc phân tán session khi scale nhiều instance.

**Lựa chọn nguồn Locale là quyết định thiết kế ứng dụng**, không phải bản chất bắt buộc của MessageSource.

## 11. Dùng LocaleContextHolder lúc nào?

Spring có `LocaleContextHolder` để truy cập locale gắn với ngữ cảnh hiện tại:

~~~java
import java.util.Locale;
import org.springframework.context.i18n.LocaleContextHolder;

Locale locale = LocaleContextHolder.getLocale();
~~~

Trong luồng xử lý request Spring MVC, framework thường thiết lập locale context để code đang chạy có thể truy cập.

Ví dụ:

~~~java
String text = messageSource.getMessage(
        "error.request.invalid",
        null,
        LocaleContextHolder.getLocale()
);
~~~

Tuy nhiên, có một giới hạn quan trọng: `LocaleContextHolder` dựa trên context gắn với thread và **không tự bảo đảm truyền qua executor, `@Async`, scheduler hoặc mọi kiểu xử lý bất đồng bộ**.

Nếu background worker gửi email cho người dùng sau khi HTTP request đã kết thúc:

~~~java
public void sendEmail(long userId, Locale recipientLocale) {
    String subject = messageSource.getMessage(
            "notification.order.created",
            new Object[] {userId},
            recipientLocale
    );

    // Gửi email bằng subject qua email service phù hợp.
}
~~~

Truyền locale của người nhận vào tác vụ là cách dễ suy luận hơn so với cố lấy locale từ thread nền. Mặt khác, tác vụ không có request context nên `LocaleContextHolder.getLocale()` có thể dùng locale mặc định của JVM hoặc ngữ cảnh khác với mong đợi.

Không nên lưu locale của một request vào biến static dùng chung; các request chạy đồng thời có thể ảnh hưởng lẫn nhau.

## 12. Thiết kế phản hồi lỗi: giữ code ổn định, dịch message

Với REST API, nên phân biệt:

- **HTTP status**: `400`, `404`, `409` hoặc `500`.
- **Business error code**: ví dụ `USER_NOT_FOUND`, `VALIDATION_ERROR`.
- **Localized message**: câu dành cho người sử dụng cuối.
- **Details**: danh sách field lỗi hoặc tham số bổ sung nếu cần.

Ví dụ tiếng Việt:

~~~json
{
  "code": "USER_NOT_FOUND",
  "message": "Không tìm thấy người dùng có mã 42.",
  "details": []
}
~~~

Ví dụ tiếng Anh:

~~~json
{
  "code": "USER_NOT_FOUND",
  "message": "User with ID 42 was not found.",
  "details": []
}
~~~

Trong cả hai response:

- HTTP status vẫn là `404 Not Found`.
- `code` vẫn là `USER_NOT_FOUND`.
- Chỉ `message` thay đổi theo locale.

### Vì sao không dùng văn bản đã dịch làm mã lỗi?

Một frontend có thể cần hiện màn hình đăng ký lại khi nhận `ACCOUNT_LOCKED`. Nếu nó dựa trên chuỗi “Tài khoản đã bị khóa”, việc sửa bản dịch có thể vô tình làm hỏng logic frontend.

Mã lỗi ổn định thích hợp cho điều khiển chương trình và phân tích log. Văn bản dịch thích hợp cho trình bày. Hai việc không nên bị gộp làm một.

Bên cạnh đó, không phải mọi exception nội bộ đều an toàn để trả message nguyên văn cho client. Lỗi kỹ thuật có thể chứa connection string, đường dẫn file, tên bảng hoặc dữ liệu nhạy cảm; chúng cần thông điệp công khai được kiểm soát.

## 13. Ví dụ Spring Boot REST: dịch lỗi không tìm thấy

Ta xây dựng một ứng dụng nhỏ với:

~~~text
src/main/java/com/example/
  DemoApplication.java
  user/
    UserController.java
    UserNotFoundException.java
  web/
    ApiExceptionHandler.java

src/main/resources/
  application.properties
  messages.properties
  messages_vi.properties
~~~

### 13.1. Định nghĩa exception nghiệp vụ

`UserNotFoundException.java`:

~~~java
package com.example.user;

public class UserNotFoundException extends RuntimeException {

    private final long userId;

    public UserNotFoundException(long userId) {
        super("User not found");
        this.userId = userId;
    }

    public long getUserId() {
        return userId;
    }
}
~~~

Exception giữ thông tin có cấu trúc là `userId`. Trong ví dụ này, message tiếng Anh trong constructor chỉ là mô tả kỹ thuật; lớp xử lý HTTP sẽ tạo thông điệp dành cho client bằng `MessageSource`.

Một hệ thống thực tế có thể xây dựng exception base type chứa `errorCode` và argument list; không nhất thiết mỗi exception phải gắn cứng bản dịch.

### 13.2. Controller minh họa

`UserController.java`:

~~~java
package com.example.user;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/users")
public class UserController {

    @GetMapping("/{id}")
    public String findUser(@PathVariable long id) {
        // Minh họa trường hợp không tìm thấy.
        throw new UserNotFoundException(id);
    }
}
~~~

Controller cố tình ném lỗi để minh họa, không thực hiện truy vấn database.

### 13.3. Exception handler dịch thông báo

`ApiExceptionHandler.java`:

~~~java
package com.example.web;

import java.util.List;
import java.util.Locale;

import com.example.user.UserNotFoundException;
import org.springframework.context.MessageSource;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    private final MessageSource messageSource;

    public ApiExceptionHandler(MessageSource messageSource) {
        this.messageSource = messageSource;
    }

    @ExceptionHandler(UserNotFoundException.class)
    public ResponseEntity<ApiError> userNotFound(
            UserNotFoundException exception,
            Locale locale
    ) {
        String message = messageSource.getMessage(
                "error.user.not-found",
                new Object[] {exception.getUserId()},
                locale
        );

        ApiError body = new ApiError(
                "USER_NOT_FOUND",
                message,
                List.of()
        );

        return ResponseEntity
                .status(HttpStatus.NOT_FOUND)
                .body(body);
    }

    public record ApiError(
            String code,
            String message,
            List<?> details
    ) {
    }
}
~~~

Spring MVC cung cấp `Locale` hiện tại cho exception handler. `MessageSource` chọn bundle dựa trên locale đó. `List<?>` được sử dụng ở đây vì response không có field-level details; ở phần validation sẽ có một response type thích hợp hơn.

Đây là ví dụ cho ứng dụng Spring Boot sử dụng Spring MVC và Jackson. Nếu dự án là Spring WebFlux, cơ chế locale context và API handler có thể khác; không nên sao chép cấu hình MVC sang WebFlux một cách máy móc.

### 13.4. Quan sát qua curl

Request tiếng Việt:

~~~bash
curl -i \
     -H "Accept-Language: vi-VN" \
     http://localhost:8080/api/users/42
~~~

Response minh họa:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{"code":"USER_NOT_FOUND","message":"Không tìm thấy người dùng có mã 42.","details":[]}
~~~

Request tiếng Anh:

~~~bash
curl -i \
     -H "Accept-Language: en-US" \
     http://localhost:8080/api/users/42
~~~

Response minh họa:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{"code":"USER_NOT_FOUND","message":"User with ID 42 was not found.","details":[]}
~~~

Sự khác biệt nằm ở `message`, không nằm ở HTTP status hoặc business code.

## 14. Bean Validation và thông báo lỗi đa ngôn ngữ

Một phần lớn thông báo lỗi trong REST API đến từ việc validate dữ liệu đầu vào.

Ví dụ:

- Tên không được để trống.
- Email sai định dạng.
- Tuổi phải lớn hơn hoặc bằng một giá trị.
- Số lượng phải nằm trong một khoảng.

Trong Spring Boot 3.x, Bean Validation sử dụng namespace `jakarta.validation`. Dự án cần dependency phù hợp, ví dụ với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Với Gradle Groovy DSL:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
~~~

Nếu chưa có Spring MVC, ứng dụng REST còn cần web starter phù hợp, ví dụ `spring-boot-starter-web`.

### 14.1. Định nghĩa request DTO

`CreateUserRequest.java`:

~~~java
package com.example.user;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public record CreateUserRequest(

        @NotBlank(message = "{validation.user.name.required}")
        String name,

        @NotBlank(message = "{validation.user.email.required}")
        @Email(message = "{validation.user.email.invalid}")
        String email
) {
}
~~~

Cú pháp `message = "{validation.user.name.required}"` yêu cầu Bean Validation tìm template message tương ứng, thay vì sử dụng một câu cố định bên trong annotation.

Các key đã được đặt trong bundle:

~~~properties
# messages.properties
validation.user.name.required=User name is required.
validation.user.email.required=Email is required.
validation.user.email.invalid=Email address is invalid.
~~~

~~~properties
# messages_vi.properties
validation.user.name.required=Tên người dùng không được để trống.
validation.user.email.required=Email không được để trống.
validation.user.email.invalid=Địa chỉ email không hợp lệ.
~~~

Khi dùng cấu hình validation auto-configuration thông thường của Spring Boot, message interpolation có thể sử dụng `MessageSource` của ứng dụng. Nếu dự án tự khai báo validator hoặc message interpolator, cần bảo đảm nó được kết nối với nguồn thông điệp phù hợp.

### 14.2. Kích hoạt validation trong controller

~~~java
package com.example.user;

import jakarta.validation.Valid;

import java.util.Map;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/users")
public class UserCreationController {

    @PostMapping
    public Map<String, String> create(
            @Valid @RequestBody CreateUserRequest request
    ) {
        // Ví dụ đơn giản: chưa lưu vào database.
        return Map.of("name", request.name());
    }
}
~~~

Với Spring MVC, khi `@Valid` phát hiện dữ liệu không hợp lệ trong request body, framework thường ném `MethodArgumentNotValidException` trước khi controller hoàn tất xử lý.

Vì vậy, để có response lỗi nhất quán, có thể xử lý exception đó trong `@RestControllerAdvice`.

## 15. Dịch field-level validation errors trong @RestControllerAdvice

Một lỗi validation không chỉ cần câu “Dữ liệu không hợp lệ”; nó còn nên cho biết field nào bị sai.

Ví dụ schema response:

~~~json
{
  "code": "VALIDATION_ERROR",
  "message": "Dữ liệu yêu cầu không hợp lệ.",
  "details": [
    {"field": "name", "message": "Tên người dùng không được để trống."},
    {"field": "email", "message": "Địa chỉ email không hợp lệ."}
  ]
}
~~~

Trong Spring MVC, `FieldError` kế thừa từ `DefaultMessageSourceResolvable` và mang theo những message codes/arguments liên quan đến binding hoặc validation.

Vì thế, có thể dùng overload:

~~~java
messageSource.getMessage(fieldError, locale)
~~~

### Ví dụ exception handler

Thêm handler vào một `@RestControllerAdvice` riêng hoặc kết hợp với handler ở mục 13 trong cùng lớp khi phát triển ứng dụng thực tế. Để minh họa độc lập, ta dùng lớp:

~~~java
package com.example.web;

import java.util.List;
import java.util.Locale;

import org.springframework.context.MessageSource;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ValidationExceptionHandler {

    private final MessageSource messageSource;

    public ValidationExceptionHandler(MessageSource messageSource) {
        this.messageSource = messageSource;
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> invalidRequest(
            MethodArgumentNotValidException exception,
            Locale locale
    ) {
        String summary = messageSource.getMessage(
                "error.request.invalid",
                null,
                locale
        );

        List<FieldIssue> details = exception.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> new FieldIssue(
                        error.getField(),
                        messageSource.getMessage(error, locale)
                ))
                .toList();

        ApiError body = new ApiError(
                "VALIDATION_ERROR",
                summary,
                details
        );

        return ResponseEntity
                .status(HttpStatus.BAD_REQUEST)
                .body(body);
    }

    public record FieldIssue(
            String field,
            String message
    ) {
    }

    public record ApiError(
            String code,
            String message,
            List<FieldIssue> details
    ) {
    }
}
~~~

Ở đây:

1. `error.request.invalid` tạo thông điệp tổng quát.
2. `FieldError.getField()` cung cấp tên field của request.
3. `messageSource.getMessage(error, locale)` giải quyết những codes của field error và fallback về default message nếu cần.
4. `ResponseEntity` trả `400 Bad Request`.
5. Mã `VALIDATION_ERROR` ổn định giữa các locale.

Khi ghép các ví dụ thành một project, có thể chọn một lớp response chung và một `@RestControllerAdvice` thống nhất. Hai lớp `ApiError` trong hai ví dụ nằm trong hai lớp handler khác nhau nên không bắt buộc trùng kiểu; production API nên thống nhất schema.

### Thử bằng curl

~~~bash
curl -i -X POST \
     -H "Content-Type: application/json" \
     -H "Accept-Language: vi-VN" \
     -d '{"name":"","email":"not-an-email"}' \
     http://localhost:8080/api/users
~~~

Response minh họa:

~~~json
{
  "code": "VALIDATION_ERROR",
  "message": "Dữ liệu yêu cầu không hợp lệ.",
  "details": [
    {
      "field": "name",
      "message": "Tên người dùng không được để trống."
    },
    {
      "field": "email",
      "message": "Địa chỉ email không hợp lệ."
    }
  ]
}
~~~

Thứ tự các phần tử `details` phụ thuộc kết quả validation và cách tổng hợp lỗi; không nên xây dựng logic client dựa trên thứ tự ngầm định của các field errors.

**Lưu ý:** Bean Validation cũng có cơ chế message interpolation riêng. Khi annotation đã chỉ định template và validator đã nội suy đúng locale, `FieldError.getDefaultMessage()` thường chứa câu đã được dịch. Dùng `getMessage(error, locale)` tận dụng chuỗi codes của Spring; ở hệ thống tùy chỉnh validator, cần kiểm tra sự phối hợp để tránh dịch hai lần hoặc fallback không mong muốn.

## 16. Có nên gọi getDefaultMessage() trực tiếp?

Với một `FieldError`, có thể làm:

~~~java
String text = fieldError.getDefaultMessage();
~~~

Cách này đôi khi đã cho câu được dịch, nếu Bean Validation hoàn thành việc nội suy thông điệp.

Tuy nhiên, cần hiểu sự khác biệt:

| Cách dùng | Ý nghĩa |
|---|---|
| `fieldError.getDefaultMessage()` | Lấy default message do cơ chế binding/validation đặt trên lỗi |
| `messageSource.getMessage(fieldError, locale)` | Thử giải quyết những message codes gắn với lỗi bằng MessageSource, sau đó xử lý fallback |
| `messageSource.getMessage("error.request.invalid", null, locale)` | Lấy một thông điệp ứng dụng theo code tường minh |

Nếu tổ chức muốn kiểm soát thứ tự tìm mã lỗi ở mức field/type/constraint, việc sử dụng `MessageSourceResolvable` có thể hữu ích. Nếu chỉ cần thông điệp đã được Bean Validation nội suy, `getDefaultMessage()` cũng có thể đủ trong nhiều trường hợp.

Điểm quan trọng là chọn **một chiến lược nhất quán**, không vừa dịch trường đã dịch sẵn vừa thay thế bằng code khác một cách ngẫu nhiên.

### Các loại validation error khác nhau

Không phải mọi lỗi request đều đi qua `MethodArgumentNotValidException`:

- Validation cho `@RequestBody` thường liên quan `MethodArgumentNotValidException`.
- Binding/validation form object có thể xuất hiện qua `BindingResult` và những exception liên quan.
- Constraint trên method parameter có thể dùng đường xử lý khác, tùy phiên bản Spring và cấu hình method validation.
- JSON không đúng cú pháp có thể tạo `HttpMessageNotReadableException` trước khi Bean Validation được gọi.

Một error-handler hoàn chỉnh cần xác định rõ các trường hợp mình muốn chuyển thành thông báo công khai. `MessageSource` chỉ giải quyết bản dịch; nó không tự quyết định exception nào tương ứng với HTTP status nào.

## 17. Thiếu thông điệp: defaultMessage, exception và fallback

Một lỗi phổ biến là gọi một code chưa được khai báo.

Ví dụ:

~~~java
messageSource.getMessage(
        "error.payment.unknown",
        null,
        Locale.forLanguageTag("vi-VN")
);
~~~

Nếu không có code đó trong các bundle phù hợp và không có fallback, overload không nhận `defaultMessage` có thể ném `NoSuchMessageException`.

### Cung cấp default message tường minh

~~~java
String text = messageSource.getMessage(
        "error.payment.unknown",
        null,
        "Không xử lý được thanh toán.",
        Locale.forLanguageTag("vi-VN")
);
~~~

Cách này hữu ích khi muốn giữ chức năng vận hành ngay cả khi bản dịch bị thiếu. Tuy nhiên, nếu mỗi nơi tự tạo fallback khác nhau, sản phẩm sẽ khó quản lý nội dung và dễ bỏ sót bản dịch.

### Dùng code làm default message

Spring Boot có option:

~~~properties
spring.messages.use-code-as-default-message=true
~~~

Khi được bật trong cấu hình phù hợp, code có thể được trả về thay vì tạo lỗi thiếu message.

Ví dụ người dùng có thể nhìn thấy:

~~~text
error.payment.unknown
~~~

Điều này có thể hữu ích trong phát triển để tìm chỗ chưa có bản dịch, nhưng thường không phù hợp cho trải nghiệm người dùng cuối. Ứng dụng cần quy ước rõ khi nào thiếu bản dịch được coi là lỗi cần sửa và khi nào có fallback chấp nhận được.

### Chiến lược fallback thực tế

Một chiến lược đơn giản:

1. Bundle gốc chứa tất cả các code công khai thiết yếu.
2. Các bundle ngôn ngữ riêng chỉ override những câu đã dịch.
3. Test hoặc quy trình biên dịch nội dung phát hiện key bị thiếu.
4. Log/cảnh báo các trường hợp bất thường mà không làm lộ dữ liệu.
5. Chỉ cho phép thông điệp fallback chung với lỗi kỹ thuật không dành cho người dùng cuối.

Việc có file bundle không tự bảo đảm từng message code có mặt trong file đó.

## 18. Sắp xếp nhiều bundle bằng basename

Ứng dụng lớn có thể tách bản dịch theo nhóm, chẳng hạn thông điệp chung và thông điệp lỗi:

~~~text
src/main/resources/
  messages.properties
  messages_vi.properties
  errors.properties
  errors_vi.properties
~~~

Trong `application.properties`:

~~~properties
spring.messages.basename=messages,errors
spring.messages.encoding=UTF-8
~~~

Khi đó `MessageSource` có thể tìm code trong các basename đã khai báo. Cách phân chia giúp các nhóm chịu trách nhiệm riêng với từng bộ thông điệp.

Ví dụ:

~~~properties
# messages.properties
button.save=Save
notification.saved=Saved successfully.
~~~

~~~properties
# errors.properties
error.user.not-found=User with ID {0} was not found.
error.request.invalid=The request contains invalid data.
~~~

Không nên khai báo **cùng một key với hai ý nghĩa khác nhau** ở nhiều bundle. Thứ tự basename và quy tắc resolve có thể khiến bản dịch không phải nguồn bạn mong muốn được chọn.

### Quy ước message key

Một convention hữu ích:

~~~text
error.<domain>.<condition>
validation.<entity>.<field>.<rule>
notification.<domain>.<action>
label.<screen>.<name>
~~~

Ví dụ:

~~~text
error.user.not-found
error.order.invalid-state
validation.user.email.invalid
notification.invoice.sent
label.profile.display-name
~~~

Tên key nên biểu đạt **ý nghĩa ổn định**, không nhất thiết phản chiếu nguyên văn câu tiếng Việt hoặc tiếng Anh. Khi sửa từ ngữ mà ý nghĩa không đổi, thường không cần đổi key.

## 19. Encoding và ký tự tiếng Việt

File bản dịch chứa tiếng Việt cần được lưu đúng mã hóa. Trong dự án hiện đại, **UTF-8** là lựa chọn phù hợp.

Ví dụ:

~~~properties
greeting.hello=Xin chào!
error.user.not-found=Không tìm thấy người dùng có mã {0}.
~~~

Và:

~~~properties
spring.messages.encoding=UTF-8
~~~

Nếu editor lưu file bằng encoding khác nhưng application được cấu hình đọc UTF-8, thông điệp có thể trở thành chuỗi ký tự lỗi:

~~~text
KhÃ´ng tÃ¬m tháº¥y ...
~~~

Các bước nên thực hiện:

- Đảm bảo file `.properties` thực sự được lưu UTF-8.
- Đảm bảo cấu hình MessageSource sử dụng encoding phù hợp.
- Dùng test để xác nhận chuỗi tiếng Việt sau khi load.
- Đừng tự sửa lỗi encoding bằng cách thay thế hàng loạt ký tự trên output.
- Phân biệt lỗi encoding của source bundle với lỗi encoding khi HTTP response được gửi tới client.

Trong Java/Spring hiện đại, cần tránh áp dụng kinh nghiệm cũ một cách máy móc rằng mọi file `.properties` bắt buộc phải escape Unicode bằng `\uXXXX`. Cách đọc bundle và encoding có thể tùy implementation; hãy cấu hình và kiểm thử rõ ràng.

## 20. Thời điểm load và cập nhật bản dịch

Các message bundle đóng gói trong executable JAR thường được xem là **tài nguyên ứng dụng**. Với Spring Boot auto-configuration và `ResourceBundleMessageSource`, những file này phù hợp để ship cùng phiên bản ứng dụng.

Nếu sửa `src/main/resources/messages_vi.properties` trong source code nhưng ứng dụng đã chạy một JAR cũ, thay đổi đó không tự xuất hiện trong process đang chạy. Thông thường cần build và deploy lại artifact có bundle mới.

Có thể cấu hình thời gian cache theo property của Spring Boot:

~~~properties
spring.messages.cache-duration=10s
~~~

Nhưng **cache duration không biến một resource nằm trong JAR bất biến thành dữ liệu có thể sửa tại runtime**. Nó chỉ ảnh hưởng đến cách cache thông điệp của implementation tương ứng.

Đối với môi trường production, các bundle đóng gói cùng artifact thường dễ kiểm soát phiên bản và rollback hơn việc chỉnh sửa trực tiếp trên một máy chủ đang chạy.

## 21. Khi cần bản dịch ngoài JAR: ReloadableResourceBundleMessageSource

Nếu ứng dụng có yêu cầu cụ thể là load file dịch từ một thư mục có thể cập nhật tại runtime, Spring Framework cung cấp `ReloadableResourceBundleMessageSource`.

Ví dụ cấu hình bean tường minh:

~~~java
package com.example.i18n;

import org.springframework.context.MessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.ReloadableResourceBundleMessageSource;

@Configuration(proxyBeanMethods = false)
public class ExternalMessagesConfiguration {

    @Bean(name = "messageSource")
    MessageSource messageSource() {
        ReloadableResourceBundleMessageSource source =
                new ReloadableResourceBundleMessageSource();

        source.setBasenames("file:/opt/app/i18n/messages");
        source.setDefaultEncoding("UTF-8");
        source.setCacheSeconds(60);
        source.setFallbackToSystemLocale(false);

        return source;
    }
}
~~~

Nếu thư mục có:

~~~text
/opt/app/i18n/messages.properties
/opt/app/i18n/messages_vi.properties
/opt/app/i18n/messages_en.properties
~~~

Spring có thể đọc bộ file bên ngoài theo basename. Việc refresh phụ thuộc cấu hình cache, độ khả dụng của file và các cơ chế filesystem liên quan.

Một vài lưu ý:

- Bean tên `messageSource` do ứng dụng khai báo sẽ thay thế hoặc khiến auto-configuration mặc định của Boot không tạo bean tương ứng.
- File phải tồn tại và đọc được **trong filesystem của process hoặc container**, không phải trên máy phát triển.
- Đừng cập nhật file trong lúc đang ghi dở. Hãy dùng cơ chế triển khai tài nguyên có tính nguyên tử phù hợp.
- Cần giới hạn quyền ghi thư mục i18n; nội dung bản dịch cũng là dữ liệu được hiển thị cho người dùng.
- Caching và phát hiện sửa đổi qua filesystem có thể khác nhau theo hệ điều hành và môi trường deploy.

Chỉ chọn cơ chế reload nếu có yêu cầu vận hành thực tế. Với ứng dụng thông thường, bundle đóng gói trong JAR đơn giản và ít lỗi hơn.

## 22. Thông điệp lỗi nghiệp vụ nên được dịch ở đâu?

Có hai cách thiết kế phổ biến.

### Cách A: dịch trực tiếp trong service nghiệp vụ

~~~java
public String registerUser(Locale locale) {
    if (userAlreadyExists()) {
        return messageSource.getMessage(
                "error.user.duplicate",
                null,
                locale
        );
    }

    return "OK";
}
~~~

Cách này đơn giản với ứng dụng nhỏ, nhưng service nghiệp vụ bắt đầu phụ thuộc locale và hình thức trình bày thông điệp.

### Cách B: service ném lỗi có mã; lớp HTTP/notification dịch

~~~text
Domain Service
    |
    +-- phát hiện USER_DUPLICATE
              |
              v
      Domain Exception
        code + args
              |
              v
        API Adapter
              |
              +-- HTTP status
              +-- MessageSource + Locale
              |
              v
      { code, message, details }
~~~

Ví dụ exception có cấu trúc:

~~~java
public class BusinessException extends RuntimeException {

    private final String code;
    private final Object[] arguments;

    public BusinessException(String code, Object... arguments) {
        super(code);
        this.code = code;
        this.arguments = arguments.clone();
    }

    public String getCode() {
        return code;
    }

    public Object[] getArguments() {
        return arguments.clone();
    }
}
~~~

Service:

~~~java
if (userAlreadyExists()) {
    throw new BusinessException(
            "error.user.duplicate",
            requestedEmail
    );
}
~~~

Adapter HTTP có thể dùng `MessageSource` để dịch code theo locale request. Một email worker có thể dịch cùng code theo locale của người nhận. Logic nghiệp vụ không cần biết ngôn ngữ của người dùng.

**Cần bảo vệ data arguments.** Ví dụ `requestedEmail` có thể là dữ liệu cá nhân; không nhất thiết phải đưa nguyên giá trị đó vào mọi message hoặc log.

Với API sản phẩm lớn, có thể tách riêng `publicErrorCode` ổn định cho client và `messageCode` dành cho bản dịch. Không phải mọi exception kỹ thuật đều thích hợp chuyển trực tiếp thành message code công khai.

## 23. Lựa chọn ngôn ngữ cho notification và email

REST request thường có `Accept-Language`. Nhưng email hoặc push notification được gửi sau đó có thể không còn request hiện tại.

Ví dụ người dùng A thao tác bằng tiếng Anh, trong khi người nhận B đã chọn tiếng Việt. Email gửi cho B nên dựa trên **ngôn ngữ ưu tiên của B** chứ không tự kế thừa locale của A.

Một mô hình đơn giản:

~~~java
public void notifyOrderCreated(
        long orderId,
        Locale recipientLocale
) {
    String text = messageSource.getMessage(
            "notification.order.created",
            new Object[] {orderId},
            recipientLocale
    );

    notificationGateway.send(text);
}
~~~

`notificationGateway` là dependency minh họa do ứng dụng định nghĩa.

Trong hệ thống thật, có thể xác định locale theo chính sách:

1. Lựa chọn đã lưu trong hồ sơ người nhận, nếu hợp lệ.
2. Ngôn ngữ của nội dung hoặc nhóm khách hàng, nếu được quy định.
3. Ngôn ngữ mặc định của sản phẩm khi thiếu lựa chọn.
4. Trường hợp request tương tác trực tiếp: tôn trọng header `Accept-Language` khi thích hợp.

Không nên dùng IP address để tự suy đoán ngôn ngữ một cách cứng nhắc. Người dùng ở một quốc gia có thể muốn một ngôn ngữ khác.

## 24. Format số, ngày và đơn vị trong thông điệp

Lựa chọn ngôn ngữ đôi khi đi kèm các quy tắc định dạng.

Ví dụ:

~~~properties
notification.items.count=You have {0} items.
~~~

Với `MessageFormat`, argument là number, date hoặc một kiểu khác có thể được format theo locale.

Một message format minh họa:

~~~properties
report.generated-at=Report generated at {0,date,short}.
~~~

Nếu truyền `java.util.Date`:

~~~java
String text = messageSource.getMessage(
        "report.generated-at",
        new Object[] {new java.util.Date()},
        Locale.US
);
~~~

Dấu phân cách ngày và định dạng có thể khác theo locale.

### Không đánh đồng format với nghiệp vụ

Tiền tệ của một giao dịch không được tự thay đổi chỉ vì header `Accept-Language` đổi từ `vi-VN` sang `en-US`. Currency code, số tiền và quy tắc kế toán phải do dữ liệu nghiệp vụ quyết định.

Tương tự, time zone cần được xử lý rõ ràng khi định dạng thời điểm. `Locale` không tự cung cấp múi giờ đúng cho từng người dùng.

Với trường hợp yêu cầu số nhiều/phức tạp theo ngữ pháp, `MessageFormat` truyền thống có giới hạn. Không nên suy luận rằng thêm một placeholder là đủ để giải quyết mọi ngôn ngữ. Những hệ thống cần pluralization phong phú có thể cân nhắc công cụ i18n chuyên dụng và quy trình dịch chuyên nghiệp.

## 25. Kiểm thử MessageSource không cần HTTP server

Có thể test trực tiếp các message bundle khi ứng dụng đã khởi tạo `MessageSource`.

Ví dụ dùng Spring Boot Test và JUnit 5:

~~~java
package com.example.i18n;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.MessageSource;

@SpringBootTest
class MessageSourceTest {

    @Autowired
    MessageSource messageSource;

    @Test
    void resolvesVietnameseMessage() {
        String actual = messageSource.getMessage(
                "error.user.not-found",
                new Object[] {"42"},
                Locale.forLanguageTag("vi-VN")
        );

        assertEquals(
                "Không tìm thấy người dùng có mã 42.",
                actual
        );
    }

    @Test
    void resolvesEnglishMessage() {
        String actual = messageSource.getMessage(
                "error.user.not-found",
                new Object[] {"42"},
                Locale.US
        );

        assertEquals(
                "User with ID 42 was not found.",
                actual
        );
    }
}
~~~

Ở đây truyền `"42"` dạng String để tránh phụ thuộc vào format số theo vùng trong phép so sánh.

Test giúp phát hiện:

- Thiếu key trong bundle.
- Sai encoding tiếng Việt.
- Placeholder không được thay.
- Fallback sai hoặc bean MessageSource chưa được cấu hình.
- Khác biệt ngoài dự kiến giữa `vi-VN` và `en-US`.

Không nên chỉ kiểm tra rằng `getMessage(...)` trả về chuỗi không rỗng, vì khi bật `use-code-as-default-message`, chuỗi đó có thể chỉ là tên code chưa được dịch.

## 26. Kiểm thử Locale ở tầng Spring MVC

Với REST API ở mục 13, có thể dùng `MockMvc` để kiểm tra `Accept-Language` ảnh hưởng đến response.

Ví dụ:

~~~java
package com.example.web;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class LocalizedApiTest {

    @Autowired
    MockMvc mvc;

    @Test
    void returnsVietnameseError() throws Exception {
        mvc.perform(get("/api/users/42")
                .header("Accept-Language", "vi-VN"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code").value("USER_NOT_FOUND"))
            .andExpect(jsonPath("$.message").value(
                    "Không tìm thấy người dùng có mã 42."
            ));
    }

    @Test
    void returnsEnglishError() throws Exception {
        mvc.perform(get("/api/users/42")
                .header("Accept-Language", "en-US"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code").value("USER_NOT_FOUND"))
            .andExpect(jsonPath("$.message").value(
                    "User with ID 42 was not found."
            ));
    }
}
~~~

Ví dụ nhắm tới Spring Boot 3.x và Spring MVC. Trong các phiên bản thư viện mới hơn, một số package hoặc annotation test có thể thay đổi; hãy dùng biến thể tương thích với version của project.

Các test này chứng minh hai điều độc lập:

1. `MessageSource` giải quyết đúng code và locale.
2. Spring MVC chuyển `Accept-Language` thành locale được dùng trong exception handler.

Chỉ test `MessageSource` trực tiếp không chứng minh toàn bộ HTTP integration đã sử dụng đúng locale.

## 27. Những lỗi thường gặp và cách điều tra

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `NoSuchMessageException` | Không tìm thấy key hoặc không có fallback | Kiểm tra basename, tên key và file theo locale |
| Trả về chính `error.user.not-found` | Bật code-as-default-message hoặc thiếu bản dịch | Kiểm tra bundle và cấu hình fallback |
| Tiếng Việt bị lỗi dấu | Encoding file không đúng hoặc decoder không phù hợp | Xác minh UTF-8 trong source và cấu hình MessageSource |
| Header `Accept-Language` không đổi response | Controller/handler dùng locale cố định hoặc resolver khác | Kiểm tra `LocaleResolver` và locale được inject |
| `?lang=vi` không có tác dụng | Resolver dùng Accept-Language, không cho set locale | Chọn cơ chế session/cookie hoặc gửi header |
| Validation vẫn hiện tiếng Anh | MessageSource/validator chưa phối hợp hoặc key thiếu | Kiểm tra annotation message template, validation config |
| Placeholder `{0}` hiện nguyên văn | Chưa truyền arguments, sai syntax hoặc chưa format | Kiểm tra overload, bundle và MessageFormat quoting |
| Locale đúng nhưng format số lạ | MessageFormat xử lý number theo vùng | Truyền identifier dưới dạng String nếu cần giữ nguyên |
| Chạy IDE đúng nhưng JAR thiếu bundle | File chưa đóng gói vào classpath | Kiểm tra `src/main/resources` và artifact |
| Thêm bản dịch nhưng process không đổi | Bản dịch nằm trong JAR cũ hoặc bị cache | Redeploy hoặc dùng cơ chế reload đúng yêu cầu |
| Background job dùng nhầm tiếng | Thread nền không có HTTP locale context | Truyền locale của người nhận tường minh |
| API lộ exception message kỹ thuật | Trả trực tiếp `exception.getMessage()` | Ánh xạ lỗi sang mã và thông điệp công khai |

### Checklist chẩn đoán theo lớp

**Lớp tài nguyên:** Bundle có tên đúng và nằm trong classpath không?

**Lớp MessageSource:** Bean `messageSource` có tồn tại không? Basename/encoding/fallback là gì?

**Lớp Locale:** Request có `Accept-Language` gì? `LocaleResolver` nào đang hoạt động? Handler nhận `Locale` nào?

**Lớp lookup:** Code có đúng không? Arguments có đúng thứ tự và kiểu không?

**Lớp API:** Exception handler có dùng message đã dịch hay đang trả exception message thô?

**Lớp validation:** Bean Validation có nội suy template bằng nguồn thông điệp mong muốn không?

Phân tách các lớp như vậy giúp điều tra có hệ thống hơn việc thay ngẫu nhiên file `messages_vi.properties` hoặc đổi tên message code nhiều lần.

## 28. Các lưu ý bảo mật và vận hành

### Không dịch nội dung kỹ thuật nhạy cảm rồi trả ra công khai

Một exception từ database có thể chứa SQL, schema name hoặc endpoint nội bộ. Nếu đem nguyên `exception.getMessage()` trả cho client, việc có MessageSource hay không không giải quyết được rủi ro thông tin.

Trong API, nên:

- Chọn một **mã lỗi công khai** đã được định nghĩa.
- Dịch câu công khai không tiết lộ implementation detail.
- Ghi thông tin kỹ thuật trong hệ thống log có kiểm soát truy cập.
- Liên kết log với request ID hoặc trace ID khi cần điều tra.
- Không đưa mật khẩu, access token hoặc dữ liệu cá nhân không cần thiết vào arguments.

### Không dịch các giá trị bắt buộc ổn định

Những giá trị máy sử dụng thường nên giữ nguyên:

~~~text
USER_NOT_FOUND
VALIDATION_ERROR
payment.status=CANCELLED
HTTP 404
traceId=...
~~~

Những chuỗi đó có thể nằm trong `code` hoặc `details` riêng. Dịch chúng tự do có thể phá hợp đồng với client.

### Bản dịch là nội dung sản phẩm

Bundle có thể chứa văn bản do đội biên tập hoặc dịch thuật duy trì. Khi quy mô tăng, cần:

- Quy trình kiểm duyệt nội dung được hiển thị.
- Kiểm tra thiếu key hoặc trùng key.
- Kiểm tra placeholder tương thích giữa các locale.
- Kiểm tra giao diện khi câu dài hơn hoặc ngắn hơn.
- Phiên bản hóa bundle đồng bộ với chức năng ứng dụng.
- Tài liệu về ngôn ngữ được hỗ trợ và ngôn ngữ fallback.

Đừng xem bản dịch như những String rải rác chỉ có lập trình viên mới được sửa.

## 29. Bài thực hành: API lỗi hai ngôn ngữ

### Bài 1 — Tạo bundle cơ sở và bản dịch

Tạo:

~~~text
src/main/resources/messages.properties
src/main/resources/messages_vi.properties
~~~

Thêm key:

~~~properties
# messages.properties
error.product.not-found=Product {0} was not found.
~~~

~~~properties
# messages_vi.properties
error.product.not-found=Không tìm thấy sản phẩm {0}.
~~~

Inject `MessageSource` và gọi với `Locale.ENGLISH`, `Locale.forLanguageTag("vi-VN")`.

**Mục tiêu:** cùng code và argument cho hai thông điệp tương ứng.

### Bài 2 — Dùng Accept-Language ở controller

Thêm endpoint:

~~~java
@GetMapping("/api/demo/product-error/{id}")
public String productError(
        @PathVariable String id,
        Locale locale
) {
    return messageSource.getMessage(
            "error.product.not-found",
            new Object[] {id},
            locale
    );
}
~~~

Thử với:

~~~bash
curl -H "Accept-Language: vi-VN" \
     http://localhost:8080/api/demo/product-error/P100
~~~

Và:

~~~bash
curl -H "Accept-Language: en-US" \
     http://localhost:8080/api/demo/product-error/P100
~~~

**Mục tiêu:** xác nhận `Locale` của request đi vào MessageSource. Endpoint minh họa chỉ trả String; trong API thực tế nên trả response lỗi có status và mã lỗi phù hợp.

### Bài 3 — Thử thiếu key

Gọi:

~~~java
messageSource.getMessage(
        "error.unknown.code",
        null,
        Locale.US
);
~~~

Quan sát hành vi thiếu message. Sau đó thử overload có `defaultMessage`.

**Mục tiêu:** hiểu rõ khác biệt giữa fallback và `NoSuchMessageException`.

### Bài 4 — Thử lỗi Bean Validation

Thêm `@NotBlank(message = "{validation.user.name.required}")` vào DTO, sau đó gửi `name` rỗng với hai header khác nhau. Xác định lỗi được nội suy ở lớp Bean Validation hay lấy lại từ Spring `MessageSourceResolvable`.

**Mục tiêu:** trả field-level message đúng ngôn ngữ, không chỉ thông điệp tổng quát.

### Bài 5 — Đổi ngôn ngữ bằng session

Dùng `SessionLocaleResolver` và `LocaleChangeInterceptor`, gửi:

~~~text
GET /greeting?lang=vi-VN
GET /greeting?lang=en-US
~~~

Kiểm tra các request liên tiếp trong cùng HTTP session.

**Mục tiêu:** phân biệt ngôn ngữ do request header quyết định với ngôn ngữ được lưu trong session.

### Bài 6 — Thông báo gửi nền

Giả sử có một job gửi email cho hai người nhận, mỗi người có locale riêng. Truyền locale tường minh vào hàm tạo thông báo thay vì dựa trên `LocaleContextHolder`.

**Mục tiêu:** tránh trộn lẫn ngôn ngữ giữa các người nhận hoặc thread.

## 30. Cách tổ chức mã nguồn nên dùng

Một cấu trúc nhỏ nhưng dễ mở rộng:

~~~text
src/main/java/com/example/
  DemoApplication.java
  i18n/
    LocaleConfiguration.java
    LocalizedMessageService.java
  user/
    CreateUserRequest.java
    UserController.java
    UserNotFoundException.java
  web/
    ApiExceptionHandler.java
    ValidationExceptionHandler.java

src/main/resources/
  application.properties
  messages.properties
  messages_vi.properties
  messages_vi_VN.properties
~~~

Ranh giới trách nhiệm:

| Thành phần | Trách nhiệm |
|---|---|
| `messages*.properties` | Nội dung và placeholder của thông điệp |
| `MessageSource` | Tìm thông điệp theo code, arguments và locale |
| `LocaleResolver` | Xác định locale của HTTP request |
| Domain/service | Xác định trạng thái nghiệp vụ và điều kiện lỗi |
| Exception handler | Chọn HTTP status, public error code, localized message |
| Bean Validation | Kiểm tra ràng buộc đầu vào |
| Background notification | Chọn locale của người nhận và tạo thông điệp ngoài HTTP request |

Khi thông điệp được dùng ở nhiều kênh, một service chuyên biệt có thể làm lớp bao quanh `MessageSource` để hạn chế các string code rải rác. Không nhất thiết tạo abstraction phức tạp cho project nhỏ, nhưng tránh để tất cả controller, service và worker tự đặt các key không thống nhất.

## 31. Những hiểu lầm thường gặp

**“MessageSource tự biết ngôn ngữ của mỗi người dùng.”** Không. Caller hoặc môi trường Spring phải cung cấp `Locale`, và ứng dụng cần chính sách lựa chọn locale.

**“Accept-Language luôn là ngôn ngữ người dùng đã chọn trong hồ sơ.”** Không. Đây là tín hiệu client gửi theo request. Profile preference có thể khác.

**“Cứ tạo messages_vi.properties là Spring Boot chắc chắn tự cấu hình.”** Chưa đủ trong mọi cấu hình. Cần bundle gốc hoặc cấu hình message source phù hợp.

**“@Value và MessageSource giống nhau.”** Không. `@Value` lấy cấu hình hoặc tài nguyên qua cơ chế injection; `MessageSource` tra thông điệp theo locale.

**“Chỉ cần dùng String.format() cho mọi ngôn ngữ.”** Không. Trật tự từ, số và quy ước vùng khác nhau. Message bundles + MessageFormat cho phép từng bản dịch điều chỉnh câu.

**“ApplicationContext có MessageSource thì mọi exception tự được dịch.”** Không. Exception handler, validation hoặc lớp trình bày cần thực sự sử dụng nguồn thông điệp.

**“Locale của HTTP request sẽ tự đi theo @Async.”** Không bảo đảm. Hãy truyền locale cần dùng vào tác vụ nền.

**“Không có bản dịch thì luôn trả tiếng Anh.”** Chỉ đúng khi thiết kế bundle cơ sở và fallback tương ứng. Có thể gặp `NoSuchMessageException` hoặc code mặc định.

**“Locale vi-VN đồng nghĩa timezone Asia/Ho_Chi_Minh.”** Không. Ngôn ngữ/vùng và múi giờ là hai khái niệm độc lập.

**“Có thể đổi ngôn ngữ bằng ?lang=vi với bất kỳ LocaleResolver nào.”** Không. Resolver dựa trên Accept-Language không cung cấp cùng cơ chế set locale như resolver dùng session/cookie.

**“Mã lỗi và câu đã dịch có thể dùng thay thế nhau.”** Không nên. Mã ổn định dành cho chương trình; câu dịch dành cho người dùng.

**“Đổi cache-duration sẽ cập nhật ngay nội dung trong JAR đã deploy.”** Không. Bundle trong artifact đóng gói không tự thay đổi vì một cấu hình cache.

## Kết luận

**`MessageSource`** là cơ chế chuẩn của Spring để lấy thông điệp từ **message code + arguments + Locale**. Trong Spring Boot, việc tạo các bundle như `messages.properties` và `messages_vi.properties` giúp tách nội dung hiển thị khỏi mã Java và triển khai đa ngôn ngữ có tổ chức.

Trong ứng dụng web, **`LocaleResolver`** xác định ngôn ngữ của request; cách phổ biến với API stateless là đọc `Accept-Language`. Với website cần ghi nhớ lựa chọn bằng query parameter, session hoặc cookie, hãy chọn resolver phù hợp. Với email hoặc background task, nên truyền `Locale` của người nhận một cách tường minh.

Đối với thông báo lỗi, hãy giữ **HTTP status** và **business error code** ổn định, chỉ dịch phần **message**. Kết hợp `MessageSource` với `@RestControllerAdvice` và Bean Validation để trả thông báo có ích cho từng field, đồng thời kiểm soát fallback, encoding, placeholder và rủi ro lộ dữ liệu.

Khi ranh giới giữa **ngữ nghĩa lỗi**, **bản dịch** và **lựa chọn ngôn ngữ** được thiết kế rõ ràng, Spring Boot có thể phục vụ nhiều nhóm người dùng mà vẫn giữ API dễ tích hợp, ứng dụng dễ bảo trì và hành vi lỗi nhất quán.
