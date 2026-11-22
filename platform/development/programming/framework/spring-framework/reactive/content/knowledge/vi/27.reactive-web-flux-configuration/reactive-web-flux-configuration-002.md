# Ảnh hưởng của @EnableWebFlux tới tự cấu hình Spring Boot

**Ngữ cảnh:** Spring Framework Reactive → **Cấu hình WebFlux**.

Trong ứng dụng Spring Boot có dùng `spring-boot-starter-webflux`, Spring Boot tự cấu hình hạ tầng WebFlux để ứng dụng có thể chạy controller annotation hoặc functional endpoint mà không cần tự khai báo toàn bộ bean nền. Khi muốn thêm CORS, codec, formatter, path matching hay resource handler, bạn thường chỉ cần một class `@Configuration implements WebFluxConfigurer`.

`@EnableWebFlux` có ý nghĩa khác: annotation này bật cấu hình Java của Spring Framework bằng cách import `DelegatingWebFluxConfiguration`. Class đó kế thừa `WebFluxConfigurationSupport`. Chính bean nền này làm điều kiện của `WebFluxAutoConfiguration` trong Spring Boot không còn thỏa mãn, nên **toàn bộ WebFlux auto-configuration của Boot sẽ back off**.

Điều này không tắt Spring WebFlux. Các bean hạ tầng mặc định của Spring Framework vẫn được tạo bởi `DelegatingWebFluxConfiguration`. Điều thay đổi là Boot không còn đóng góp phần cấu hình WebFlux riêng của nó như codec customizer, static resource/WebJars mapping và welcome page. Nếu muốn giữ các tiện ích đó, hãy cấu hình bằng `WebFluxConfigurer` mà không gắn `@EnableWebFlux`.

## 1. Phân biệt ba thành phần

Trước khi xem ảnh hưởng, cần phân biệt trách nhiệm của từng thành phần:

| Thành phần | Vai trò | Khi nào xuất hiện |
|---|---|---|
| `@EnableWebFlux` | Import cấu hình Java WebFlux của Spring Framework | Khi ứng dụng chủ động yêu cầu toàn quyền cấu hình WebFlux |
| `DelegatingWebFluxConfiguration` | Tạo các bean hạ tầng mặc định và tìm các bean `WebFluxConfigurer` để ủy quyền tùy biến | Được import bởi `@EnableWebFlux`; cũng được Boot dùng trong cấu hình của nó |
| `WebFluxAutoConfiguration` | Bổ sung cấu hình WebFlux đặc thù của Spring Boot trên nền Spring Framework | Khi ứng dụng reactive và chưa có bean `WebFluxConfigurationSupport` |

`WebFluxConfigurer` là interface mở rộng cấu hình. Chỉ implement interface này **không** đồng nghĩa với việc bật lại toàn bộ cấu hình thủ công, và cũng không làm Boot auto-configuration back off.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
class ApiWebFluxConfiguration implements WebFluxConfigurer {
    // Chỉ thêm các tùy biến cần thiết.
}
```

Cấu hình trên vẫn cho Boot tham gia. Nếu thêm `@EnableWebFlux` vào class, hành vi khởi động sẽ thay đổi vì Spring Framework import `DelegatingWebFluxConfiguration`.

## 2. Điều kiện chính xác khiến Boot back off

Trong Spring Boot 3.5, `WebFluxAutoConfiguration` có điều kiện ở cấp class:

```java
@AutoConfiguration(...)
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.REACTIVE)
@ConditionalOnClass(WebFluxConfigurer.class)
@ConditionalOnMissingBean(WebFluxConfigurationSupport.class)
public class WebFluxAutoConfiguration {
    // ...
}
```

Điều kiện quan trọng là:

```java
@ConditionalOnMissingBean(WebFluxConfigurationSupport.class)
```

Spring Framework định nghĩa quan hệ kế thừa:

```text
WebFluxConfigurationSupport
          ^
          |
DelegatingWebFluxConfiguration
          ^
          |
@Import bởi @EnableWebFlux
```

Khi class cấu hình có `@EnableWebFlux` được xử lý, `DelegatingWebFluxConfiguration` được import vào context. Vì đây là subclass của `WebFluxConfigurationSupport`, điều kiện `@ConditionalOnMissingBean` của Boot không còn đúng.

Kết quả: Spring bỏ qua `WebFluxAutoConfiguration`. Đây là back off ở cấp toàn bộ auto-configuration class, không chỉ bỏ qua một bean đơn lẻ.

### 2.1. Vì sao implement WebFluxConfigurer không làm Boot back off?

Điều kiện của Boot kiểm tra bean kiểu `WebFluxConfigurationSupport`, không kiểm tra bean kiểu `WebFluxConfigurer`.

```java
@Configuration(proxyBeanMethods = false)
class CustomWebFluxConfiguration implements WebFluxConfigurer {
    // Không có @EnableWebFlux.
}
```

Class trên chỉ là một configurer được `DelegatingWebFluxConfiguration` của Boot phát hiện. Nó không tạo bean `WebFluxConfigurationSupport` mới, nên Boot tiếp tục cấu hình.

Đây là khác biệt quan trọng nhất:

| Cách cấu hình | Có bean WebFluxConfigurationSupport do người dùng thêm? | Boot WebFlux auto-config |
|---|---:|---|
| Chỉ dùng starter-webflux | Không | Hoạt động |
| `@Configuration implements WebFluxConfigurer` | Không | Hoạt động |
| `@Configuration @EnableWebFlux` | Có, qua DelegatingWebFluxConfiguration | Back off |
| Kế thừa `WebFluxConfigurationSupport` | Có | Back off |
| Kế thừa `DelegatingWebFluxConfiguration` | Có | Back off |

Không nên suy luận rằng cứ có một class cấu hình WebFlux là Boot ngừng hoạt động. Điều kiện bean cụ thể mới quyết định.

## 3. @EnableWebFlux thực sự làm gì?

Trong Spring Framework, `@EnableWebFlux` được meta-annotate với `@Import(DelegatingWebFluxConfiguration.class)`. Cấu hình được import cung cấp hạ tầng cho cả annotated controller và functional endpoint.

Những thành phần nền bao gồm:

- Handler mapping cho `@RequestMapping` và controller annotation.
- Adapter để gọi handler/controller.
- Handler cho `RouterFunction` và functional endpoint.
- `ServerCodecConfigurer` cùng các reader/writer mặc định.
- Content negotiation và path matching.
- CORS mapping, formatter/converter, validator và view resolver theo cấu hình.
- Resource handler nếu ứng dụng đăng ký qua API tương ứng.
- WebSocket handler adapter và các hạ tầng WebFlux liên quan.

Spring Framework vẫn dò dependency trên classpath để chọn codec phù hợp, ví dụ Jackson cho JSON khi dependency tương ứng có mặt. Vì vậy, thêm `@EnableWebFlux` không làm JSON hoặc controller tự biến mất. Vấn đề là các tùy chỉnh riêng của Boot không còn tự động được áp dụng qua `WebFluxAutoConfiguration`.

`@EnableWebFlux` cũng không thay thế việc khai báo controller, router, service hoặc component scan. Nó chỉ bật cấu hình hạ tầng WebFlux.

## 4. Những phần Boot WebFlux auto-configuration bổ sung

Spring Boot mô tả WebFlux auto-configuration là lớp bổ sung trên cấu hình mặc định của Spring Framework. Trong Boot 3.5, các phần đáng chú ý gồm:

| Nhóm | Boot bổ sung | Ý nghĩa khi WebFluxAutoConfiguration back off |
|---|---|---|
| HTTP codecs | Áp dụng `CodecCustomizer` và cấu hình codec của Boot | Phải kiểm tra lại cấu hình reader/writer, Jackson và giới hạn buffer |
| Static resources | Đăng ký resource handler cho thư mục static chuẩn | Tự đăng ký resource handler nếu ứng dụng cần phục vụ file |
| WebJars | Mapping tài nguyên WebJars | Tự cấu hình mapping nếu ứng dụng dùng WebJars |
| Welcome page | Tự phát hiện trang index tĩnh/template | Cần tự xử lý hoặc kiểm tra route trang chủ |
| Formatters | Áp dụng formatter/converter và thuộc tính định dạng của Boot | Tự đăng ký formatter nếu cần quy tắc riêng |
| Cấu hình handler | Boot cung cấp configurer và các bean liên quan | Cần xem lại bean mà ứng dụng tự thay thế |

Boot 3.5 triển khai phần lớn đóng góp WebFlux này qua nested class `WebFluxAutoConfiguration.WebFluxConfig`, một bean implement `WebFluxConfigurer`. Class đó áp dụng codec customizer, formatter, resource handler, argument resolver và view resolver.

Khi `@EnableWebFlux` làm outer auto-configuration back off, `WebFluxConfig` của Boot cũng không được đăng ký.

## 5. Ảnh hưởng tới HTTP codecs và JSON

Spring WebFlux dùng `HttpMessageReader` và `HttpMessageWriter` để đọc request body và ghi response body. Các codec mặc định vẫn đến từ Spring Framework, nhưng cấu hình bổ sung của Boot được áp dụng qua configurer của Boot.

Ví dụ Boot có thể áp dụng:

- Cấu hình `CodecCustomizer` do ứng dụng khai báo.
- Giới hạn buffer từ thuộc tính codec.
- Các tùy chỉnh Jackson được liên kết với codec.
- Cấu hình reader/writer theo dependency có trong classpath.

Khi `@EnableWebFlux` làm Boot WebFlux configurer biến mất, không nên mặc định các `CodecCustomizer` hoặc thuộc tính Boot sẽ được áp dụng như trước. Nếu cần kiểm soát codec, hãy cấu hình trực tiếp bằng `WebFluxConfigurer`:

```java
@Configuration(proxyBeanMethods = false)
class ApiWebFluxConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs()
                .maxInMemorySize(2 * 1024 * 1024);
    }
}
```

Đoạn code tăng giới hạn buffer mặc định lên 2 MiB cho codec được cấu hình. Nó không làm tăng vô hạn bộ nhớ và cũng không thay thế việc streaming cho payload lớn.

Nếu dùng full manual mode, cần xác định rõ:

1. Codec nào được đăng ký mặc định.
2. Có cần Jackson encoder/decoder tùy chỉnh không.
3. Có cần CBOR, XML, Protobuf hoặc codec riêng không.
4. Giới hạn bộ nhớ cho request/response aggregate là bao nhiêu.
5. Có cần log request detail hay không và dữ liệu nào được phép log.

Đừng dùng `registerDefaults(false)` nếu chưa chủ đích thay toàn bộ default codec. Gọi phương thức đó có thể loại các reader/writer mặc định mà controller đang cần.

## 6. Ảnh hưởng tới static resources, WebJars và welcome page

Spring Boot tự cấu hình phục vụ static content từ các vị trí classpath phổ biến như:

```text
classpath:/static/
classpath:/public/
classpath:/resources/
classpath:/META-INF/resources/
```

Boot cũng hỗ trợ mapping WebJars và phát hiện welcome page như `index.html` hoặc template `index`. Các thuộc tính thường gặp trong Boot 3.5:

```properties
spring.webflux.static-path-pattern=/assets/**
spring.webflux.webjars-path-pattern=/webjars/**
spring.web.resources.static-locations=classpath:/public/
```

Khi dùng `@EnableWebFlux`, Boot WebFlux auto-configuration back off. Không nên cho rằng các mapping static/WebJars/welcome page do `WebFluxAutoConfiguration` đăng ký vẫn tồn tại.

Nếu cần phục vụ static resource trong manual mode, đăng ký rõ:

```java
@Configuration(proxyBeanMethods = false)
@EnableWebFlux
class ManualWebFluxConfiguration implements WebFluxConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/static/");
    }
}
```

Đây là cấu hình tối thiểu. Nếu cần cache control, versioned resource, compressed resource hoặc WebJars, phải cấu hình thêm resolver/transformer và mapping tương ứng.

Không đăng ký resource handler quá rộng nếu route API cũng dùng cùng path pattern. Hãy xác định thứ tự và phạm vi mapping để file tĩnh không che endpoint ứng dụng.

## 7. Formatters, converters và validator

Boot có thể bổ sung formatter/converter dựa trên bean và thuộc tính cấu hình. Các thuộc tính định dạng WebFlux có thể gồm:

```properties
spring.webflux.format.date=yyyy-MM-dd
spring.webflux.format.time=HH:mm:ss
spring.webflux.format.date-time=yyyy-MM-dd'T'HH:mm:ss
```

Các giá trị ví dụ phải phù hợp định dạng và nhu cầu locale của API. Nếu Boot configurer không còn hoạt động, đừng mặc định các thuộc tính này đã được gắn vào ConversionService của WebFlux.

Bạn có thể đăng ký formatter qua `WebFluxConfigurer`:

```java
@Configuration(proxyBeanMethods = false)
class DateFormatConfiguration implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        DateTimeFormatterRegistrar registrar =
                new DateTimeFormatterRegistrar();

        registrar.setUseIsoFormat(true);
        registrar.registerFormatters(registry);
    }
}
```

Với Bean Validation, Spring Framework có cơ chế đăng ký validator mặc định khi provider tương ứng có mặt trên classpath. Tuy nhiên, nếu dựa vào validator hoặc conversion service được Boot tùy chỉnh, hãy kiểm tra bean thực tế trong context sau khi thêm `@EnableWebFlux`.

Có thể cung cấp `Validator` qua `WebFluxConfigurer#getValidator()` nếu cần validator toàn cục riêng. Validator cục bộ vẫn có thể được đăng ký bằng `@InitBinder` trong controller.

## 8. Điều gì vẫn hoạt động khi @EnableWebFlux được thêm?

Back off của `WebFluxAutoConfiguration` không đồng nghĩa tắt toàn bộ Spring Boot auto-configuration.

Các phần sau có auto-configuration và điều kiện riêng, nên không được kết luận chúng tự động biến mất chỉ vì có `@EnableWebFlux`:

- Reactive web server factory và cấu hình cổng/SSL của server.
- Error handling của Boot qua `ErrorWebFluxAutoConfiguration`.
- Spring Security reactive và filter chain.
- Actuator và các integration dựa trên điều kiện riêng.
- Data access, messaging, scheduling, serialization hoặc auto-configuration không thuộc WebFluxAutoConfiguration.
- Bean do ứng dụng tự khai báo.

Tuy nhiên, một auto-configuration độc lập có thể phụ thuộc bean hạ tầng do WebFlux cung cấp. Khi tự thay cấu hình, hãy xác nhận các dependency cần thiết vẫn tồn tại và tương thích.

`@EnableWebFlux` cũng không tự chuyển một ứng dụng servlet thành reactive. Nếu cùng có `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thường chọn Spring MVC. Việc chọn application type là một quyết định riêng; nếu thật sự cần reactive mode trong classpath có cả hai starter, xem xét `spring.main.web-application-type=reactive`.

## 9. Cách khuyến nghị: WebFluxConfigurer không có @EnableWebFlux

Nếu chỉ cần tùy chỉnh một vài phần, giữ Boot auto-configuration và thêm configurer:

```java
@Configuration(proxyBeanMethods = false)
class ApiWebFluxConfiguration implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://frontend.example")
                .allowedMethods("GET", "POST");
    }

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs()
                .maxInMemorySize(2 * 1024 * 1024);
    }
}
```

Không có `@EnableWebFlux`. Khi khởi động:

1. Boot thấy reactive web application và các class WebFlux trên classpath.
2. Không có bean `WebFluxConfigurationSupport` do người dùng khai báo.
3. `WebFluxAutoConfiguration` được áp dụng.
4. `WebFluxAutoConfiguration.WebFluxConfig` được đăng ký.
5. `DelegatingWebFluxConfiguration` tổng hợp Boot configurer và configurer của ứng dụng.
6. CORS và giới hạn codec do ứng dụng yêu cầu được bổ sung vào cấu hình WebFlux.

Đây là cách phù hợp cho đa số ứng dụng Boot. Bạn chỉ khai báo phần khác biệt; Boot vẫn quản lý phần còn lại.

## 10. Khi nào nên dùng @EnableWebFlux?

Chỉ dùng `@EnableWebFlux` khi ứng dụng chủ động nhận trách nhiệm cấu hình hạ tầng WebFlux, ví dụ:

- Ứng dụng Spring Framework không dùng Spring Boot auto-configuration.
- Muốn tự quản lý hoàn toàn codec, resource handler, view resolver, validator và conversion service.
- Có yêu cầu đặc biệt không thể đáp ứng bằng API `WebFluxConfigurer`.
- Đang xây dựng cấu hình framework nội bộ với bean hạ tầng do nhóm tự quản lý.
- Cần kiểm soát trực tiếp các bean được khai báo từ `WebFluxConfigurationSupport`.

Nếu chỉ cần thêm CORS hoặc đổi giới hạn codec, việc bật full manual mode thường làm tăng số cấu hình phải tự chịu trách nhiệm.

Trước khi dùng, hãy lập danh sách những tính năng Boot đang cung cấp cho ứng dụng và cách thay thế chúng. Đặc biệt kiểm tra static resources, WebJars, welcome page, codec customizer, formatter, validator và cấu hình view.

## 11. Không gắn @EnableWebFlux vào thư viện dùng chung một cách tùy tiện

Một starter hoặc thư viện nội bộ thường được import vào nhiều ứng dụng Boot khác nhau. Nếu thư viện chứa config class có `@EnableWebFlux`, nó có thể làm `WebFluxAutoConfiguration` của ứng dụng chủ back off.

Hậu quả có thể xuất hiện ở một ứng dụng khác với ứng dụng thư viện được phát triển ban đầu:

- Static resources hoặc welcome page không còn mapping như mong đợi.
- Codec customizer của Boot không được áp dụng qua Boot WebFlux configurer.
- Các thuộc tính Boot-specific không được dùng như trước.
- Người dùng phải tự khai báo thêm hạ tầng vốn trước đó có sẵn.

Với thư viện cần bổ sung WebFlux customization, hãy ưu tiên cung cấp một bean `WebFluxConfigurer` hoặc một auto-configuration nhỏ có điều kiện phù hợp, không áp đặt `@EnableWebFlux` lên ứng dụng chủ.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
class LibraryWebFluxConfigurer implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/library-api/**")
                .allowedMethods("GET");
    }
}
```

Thư viện cần tránh ghi đè cấu hình của ứng dụng chủ nếu không có lý do rõ ràng. Nếu cung cấp bean có thể thay thế, dùng điều kiện như `@ConditionalOnMissingBean` theo đúng thiết kế starter.

## 12. Nhiều WebFluxConfigurer và thứ tự áp dụng

Spring cho phép nhiều bean `WebFluxConfigurer` cùng tồn tại. `DelegatingWebFluxConfiguration` phát hiện các configurer và gọi các callback tương ứng để hợp thành cấu hình.

Ví dụ ứng dụng có:

- Boot configurer: cấu hình codecs, static resources, formatter và view.
- Cấu hình CORS: khai báo allowed origin/method.
- Cấu hình API: thêm path prefix hoặc content type resolver.
- Cấu hình codec riêng: thêm decoder hoặc thay đổi giới hạn bộ nhớ.

Khi thứ tự callback có ý nghĩa, có thể sắp xếp configurer bằng `@Order` hoặc `Ordered`. Không dựa vào thứ tự component scan hay thứ tự file Java.

Tránh nhiều configurer cùng sửa một thiết lập theo các giá trị mâu thuẫn. Hãy chọn một chủ sở hữu rõ cho mỗi chính sách và viết integration test để kiểm tra kết quả hợp nhất.

## 13. WebHttpHandlerBuilderCustomizer là một điểm mở rộng khác

Không phải mọi tùy biến đều cần `WebFluxConfigurer`. Spring Boot cho phép khai báo bean `WebHttpHandlerBuilderCustomizer` để sửa `WebHttpHandlerBuilder` đã được auto-configure.

Dùng điểm mở rộng này khi cần tùy chỉnh cấp HTTP handler, chẳng hạn bổ sung thành phần vào chuỗi xử lý thấp hơn controller configuration.

```java
@Bean
WebHttpHandlerBuilderCustomizer httpHandlerCustomizer() {
    return builder -> {
        // Add a custom WebExceptionHandler or WebFilter
        // only when the application requires that behavior.
    };
}
```

Đây là snippet minh họa; cần import `org.springframework.boot.web.reactive.server.WebHttpHandlerBuilderCustomizer` và cung cấp implementation thực tế.

Hãy chọn đúng tầng:

| Nhu cầu | Điểm mở rộng phù hợp |
|---|---|
| CORS, formatter, codec, path matching | `WebFluxConfigurer` |
| Static resource mapping | `WebFluxConfigurer#addResourceHandlers` |
| WebFilter cấp request/response | Bean `WebFilter` |
| Tùy biến HTTP handler builder | `WebHttpHandlerBuilderCustomizer` |
| Toàn quyền cấu hình WebFlux infrastructure | `@EnableWebFlux` / advanced configuration |

Không dùng customizer cấp thấp để thay thế một callback WebFlux đã có sẵn.

## 14. Advanced configuration mode

Nếu `WebFluxConfigurer` không cung cấp callback cần thiết, Spring Framework có chế độ nâng cao. Tài liệu Framework mô tả việc kế thừa `DelegatingWebFluxConfiguration` để override bean declaration trong khi vẫn có thể phát hiện các configurer khác.

Ví dụ khung:

```java
@Configuration(proxyBeanMethods = false)
class AdvancedWebFluxConfiguration
        extends DelegatingWebFluxConfiguration {

    // Override only the infrastructure bean or hook
    // that the application truly needs to replace.
}
```

Trong Spring Boot, đây cũng là lựa chọn có chủ đích để thay quyền sở hữu cấu hình. Vì `DelegatingWebFluxConfiguration` kế thừa `WebFluxConfigurationSupport`, điều kiện của `WebFluxAutoConfiguration` sẽ không còn thỏa mãn. Hãy chuẩn bị cấu hình thay thế cho các phần Boot trước đó cung cấp.

Không kết hợp tùy tiện `@EnableWebFlux` với việc kế thừa một configuration support class khác. Chỉ nên có một nguồn chịu trách nhiệm import/tạo WebFlux infrastructure để tránh duplicate bean hoặc cấu hình không nhất quán.

## 15. So sánh trước và sau khi thêm @EnableWebFlux

Giả sử ứng dụng ban đầu chỉ dùng `spring-boot-starter-webflux`:

| Hành vi | Không có @EnableWebFlux | Có @EnableWebFlux |
|---|---|---|
| Spring WebFlux infrastructure | Có | Có |
| Boot WebFluxAutoConfiguration | Có | Back off |
| Boot WebFluxConfig | Có | Không |
| Spring default codecs | Có | Có |
| Boot CodecCustomizer được áp dụng qua WebFluxConfig | Có | Không tự động qua configurer của Boot |
| Boot static/WebJars mappings | Có | Cần tự cấu hình nếu muốn |
| Boot welcome page configuration | Có | Không được cung cấp bởi WebFluxAutoConfiguration |
| WebFluxConfigurer của ứng dụng | Được phát hiện | Được phát hiện bởi Delegating config |
| Reactive server auto-config riêng | Theo điều kiện riêng | Không bị tắt chỉ bởi annotation |
| Security/Error/Actuator auto-config riêng | Theo điều kiện riêng | Không bị blanket-disable |

Đừng hiểu bảng này như danh sách mọi bean trong context. Phiên bản Boot, dependency và bean do ứng dụng cung cấp đều ảnh hưởng kết quả. Hãy dùng Condition Evaluation Report hoặc kiểm thử ApplicationContext để xác định chính xác cấu hình nào đã match.

## 16. Cách kiểm tra auto-configuration đã back off

Có ba cách hữu ích:

1. **Condition Evaluation Report:** chạy ứng dụng với debug hoặc xem Actuator conditions endpoint nếu endpoint được expose an toàn.
2. **ApplicationContext test:** kiểm tra bean Boot configurer có xuất hiện hay không.
3. **Integration test HTTP:** kiểm tra hành vi mà ứng dụng cần như JSON codec, static resource, CORS và welcome page.

Ví dụ test context nên kiểm tra class configurer của Boot thay vì chỉ kiểm tra một controller chạy được. Controller có thể vẫn hoạt động sau khi Boot WebFlux auto-config back off, nên riêng việc endpoint trả 200 không chứng minh toàn bộ cấu hình vẫn còn.

## 17. Ví dụ Java 17+ chạy được: Boot app giữ auto-configuration

Project mẫu dùng Spring Boot 3.5.16, Java 17 và WebFlux.

Cấu trúc:

```text
webflux-enable-config-demo/
├── pom.xml
├── src/main/java/demo/WebFluxApplication.java
├── src/main/java/demo/ApiWebFluxConfiguration.java
├── src/main/java/demo/HealthController.java
└── src/test/java/demo/EnableWebFluxAutoConfigurationTest.java
```

### 17.1. pom.xml

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

    <groupId>demo</groupId>
    <artifactId>webflux-enable-config-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

### 17.2. WebFluxApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebFluxApplication.class, args);
    }
}
```

### 17.3. ApiWebFluxConfiguration.java

```java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class ApiWebFluxConfiguration implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://frontend.example")
                .allowedMethods("GET", "POST");
    }

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs()
                .maxInMemorySize(2 * 1024 * 1024);
    }
}
```

Điểm quan trọng: class không có `@EnableWebFlux`. Boot vẫn đăng ký `WebFluxAutoConfiguration.WebFluxConfig` và kết hợp các callback của configurer này với cấu hình mặc định.

### 17.4. HealthController.java

```java
package demo;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class HealthController {

    @GetMapping("/health")
    public Mono<Map<String, String>> health() {
        return Mono.just(Map.of("status", "UP"));
    }
}
```

Chạy ứng dụng:

```bash
mvn spring-boot:run
```

Kiểm tra endpoint:

```bash
curl -i http://localhost:8080/api/health
```

Body JSON dự kiến:

```json
{"status":"UP"}
```

Response có status HTTP 200 và Content-Type JSON tương ứng. Thứ tự thuộc tính JSON không phải contract cần dựa vào; điều quan trọng là object được serialize đúng.

## 18. Kiểm thử hai chế độ bằng ReactiveWebApplicationContextRunner

Để chứng minh khác biệt ở cấp context, có thể kiểm tra sự hiện diện của Boot configurer:

```java
package demo;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.web.reactive.WebFluxAutoConfiguration;
import org.springframework.boot.test.context.runner.ReactiveWebApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.DelegatingWebFluxConfiguration;
import org.springframework.web.reactive.config.EnableWebFlux;
import org.springframework.web.reactive.config.WebFluxConfigurer;

import static org.assertj.core.api.Assertions.assertThat;

class EnableWebFluxAutoConfigurationTest {

    private final ReactiveWebApplicationContextRunner runner =
            new ReactiveWebApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    WebFluxAutoConfiguration.class));

    @Test
    void plainWebFluxConfigurerKeepsBootConfiguration() {
        runner.withUserConfiguration(PlainConfigurer.class)
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(
                                    WebFluxAutoConfiguration.WebFluxConfig.class);

                    assertThat(context)
                            .hasSingleBean(
                                    WebFluxAutoConfiguration.EnableWebFluxConfiguration.class);
                });
    }

    @Test
    void enableWebFluxMakesBootAutoConfigurationBackOff() {
        runner.withUserConfiguration(ManualEnableWebFlux.class)
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(WebFluxAutoConfiguration.class);

                    assertThat(context)
                            .doesNotHaveBean(
                                    WebFluxAutoConfiguration.WebFluxConfig.class);

                    assertThat(context)
                            .hasSingleBean(
                                    DelegatingWebFluxConfiguration.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class PlainConfigurer implements WebFluxConfigurer {
    }

    @Configuration(proxyBeanMethods = false)
    @EnableWebFlux
    static class ManualEnableWebFlux implements WebFluxConfigurer {
    }
}
```

Test thứ nhất tạo reactive context chỉ có một `WebFluxConfigurer` thông thường. Boot WebFlux configurer vẫn xuất hiện.

Test thứ hai thêm `@EnableWebFlux`. Spring import `DelegatingWebFluxConfiguration`; bean nền `WebFluxConfigurationSupport` làm điều kiện Boot không còn đúng, nên `WebFluxAutoConfiguration` và nested `WebFluxConfig` không được đăng ký.

Chạy test:

```bash
mvn test
```

Hai test chứng minh khác biệt về auto-configuration mà không cần mở socket HTTP. Integration test của ứng dụng ở phần trước vẫn hữu ích để kiểm tra codec, CORS và resource behavior qua request thực tế.

## 19. Nếu thật sự muốn dùng @EnableWebFlux trong Boot

Nếu quyết định nhận toàn quyền cấu hình, hãy tạo một cấu hình rõ ràng:

```java
@Configuration(proxyBeanMethods = false)
@EnableWebFlux
class ManualWebFluxConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs()
                .maxInMemorySize(2 * 1024 * 1024);
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/static/");
    }
}
```

Sau đó rà soát và bổ sung những phần Boot trước đây đã tự cung cấp:

- Static resources và WebJars.
- Welcome page.
- Codec customizer, Jackson settings và buffer limits.
- Formatter/converter và validator.
- View resolver nếu ứng dụng render HTML/template.
- CORS, path matching và argument resolver.
- Các customizer/hạ tầng khác mà ứng dụng đang phụ thuộc.

Không cần tự viết lại mọi thứ một cách máy móc. Chỉ cấu hình những phần thực sự dùng và kiểm thử contract của ứng dụng. Nếu một auto-configuration độc lập còn hoạt động, xác nhận nó vẫn nhận đủ bean phụ thuộc.

## 20. Lỗi thường gặp

1. **Thêm @EnableWebFlux chỉ để thêm CORS.** Boot auto-config có thể back off; dùng WebFluxConfigurer không có annotation.
2. **Nghĩ @EnableWebFlux tắt toàn bộ Spring Boot.** Nó làm WebFluxAutoConfiguration back off; auto-configuration khác có điều kiện riêng.
3. **Nghĩ WebFluxConfigurer làm Boot back off.** Điều kiện kiểm tra WebFluxConfigurationSupport, không phải WebFluxConfigurer.
4. **Cho rằng WebFlux ngừng hoạt động khi Boot back off.** DelegatingWebFluxConfiguration vẫn cung cấp hạ tầng Spring Framework.
5. **Không kiểm tra codec sau khi thêm annotation.** Codec mặc định vẫn có, nhưng Boot CodecCustomizer có thể không được áp dụng qua WebFluxConfig.
6. **Mất static resource mapping mà không biết.** Boot-specific resource handler có thể không còn; kiểm tra /static, WebJars và welcome page.
7. **Dựa vào spring.webflux.static-path-pattern trong manual mode.** Tự đăng ký ResourceHandlerRegistry nếu Boot configurer không còn áp dụng.
8. **Dựa vào thuộc tính codec nhưng không kiểm tra phiên bản.** Boot 3.5 dùng spring.http.codecs.*; phiên bản trước có thể dùng spring.codec.*.
9. **Cho rằng mọi thuộc tính Boot đều mất.** Chỉ những thuộc tính được tiêu thụ bởi auto-configuration đã back off bị ảnh hưởng; property của subsystem khác có thể vẫn hoạt động.
10. **Thêm nhiều @EnableWebFlux.** Chỉ nên có một configuration import WebFlux infrastructure; dùng nhiều WebFluxConfigurer cho các phần tùy biến.
11. **Đăng ký nhiều configurer cùng sửa một codec.** Có thể tạo kết quả khó đoán; xác định một nơi sở hữu policy.
12. **Dùng @EnableWebFlux trong thư viện dùng chung.** Có thể làm ứng dụng chủ mất Boot WebFlux auto-config.
13. **Nhầm WebFlux auto-config với reactive server auto-config.** Server factory có điều kiện riêng và không bị tắt chỉ bởi annotation.
14. **Cho rằng error handler Boot chắc chắn biến mất.** ErrorWebFluxAutoConfiguration là auto-configuration riêng; kiểm tra điều kiện của nó.
15. **Dùng WebFluxConfigurer cho tùy biến HTTP handler cấp thấp.** Cân nhắc WebHttpHandlerBuilderCustomizer nếu đúng tầng.
16. **Kế thừa WebFluxConfigurationSupport nhưng mong Boot tiếp tục auto-config.** Kế thừa class này cũng làm điều kiện missing bean không thỏa.
17. **Thêm @EnableWebFlux để đổi MVC sang reactive.** Application type là quyết định riêng; annotation không thay thế lựa chọn web application type.
18. **Không dùng Condition Evaluation Report.** Khi context khác dự kiến, xem điều kiện nào match/back off thay vì đoán từ một endpoint.
19. **Chỉ test controller trả 200.** Controller có thể chạy ở cả hai mode; cần test Boot configurer và các tính năng Boot mà ứng dụng phụ thuộc.
20. **Tự cấu hình toàn bộ codec nhưng quên default.** Chỉ tắt default codec khi thực sự muốn thay thế và đã đăng ký đủ reader/writer.

## 21. Checklist trước khi thêm @EnableWebFlux

Trước khi commit thay đổi, hãy trả lời:

- Ứng dụng dùng Spring Framework thuần hay Spring Boot?
- Có đang dùng `spring-boot-starter-webflux` không?
- Mục đích là thêm một vài callback hay nhận toàn quyền cấu hình?
- Có thể dùng `WebFluxConfigurer` mà không có `@EnableWebFlux` không?
- Boot WebFluxAutoConfiguration có đang cung cấp codec, static resource, WebJars hoặc welcome page mà ứng dụng cần?
- Các thuộc tính `spring.webflux.*` và codec có được cấu hình bởi Boot WebFluxConfig không?
- Có cần tự cấu hình formatter, validator, CORS, view resolver hoặc path matching?
- Các auto-configuration độc lập như server, error handling, Security và Actuator còn hoạt động theo điều kiện riêng không?
- Có test context chứng minh bean Boot configurer xuất hiện hoặc back off như dự kiến?
- Có integration test cho JSON codec, static resource, CORS và endpoint chính?
- Có thư viện nào trong ứng dụng vô tình import `@EnableWebFlux` không?
- Có chỉ một nơi chịu trách nhiệm tạo WebFlux infrastructure không?

**Ghi nhớ:** Trong Spring Boot, `@EnableWebFlux` import `DelegatingWebFluxConfiguration`, một subclass của `WebFluxConfigurationSupport`. Điều đó làm `@ConditionalOnMissingBean(WebFluxConfigurationSupport.class)` của `WebFluxAutoConfiguration` không còn thỏa mãn, nên Boot WebFlux auto-configuration back off. Spring WebFlux vẫn chạy bằng infrastructure của Framework. Nếu chỉ muốn tùy biến CORS, codec, formatter hoặc path matching, hãy dùng `WebFluxConfigurer` mà không có `@EnableWebFlux` để giữ cấu hình Boot. Chỉ bật annotation khi đã chủ động thay thế các phần Boot-specific mà ứng dụng cần.

## Tài liệu tham khảo

- Spring Boot 3.5 — [Reactive Web Applications: WebFlux auto-configuration](https://docs.spring.io/spring-boot/reference/web/reactive.html).
- Spring Boot 3.5 — [WebFluxAutoConfiguration Javadoc and its ConditionalOnMissingBean condition](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/reactive/WebFluxAutoConfiguration.html).
- Spring Boot 3.5 — [WebFluxAutoConfiguration.WebFluxConfig Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/reactive/WebFluxAutoConfiguration.WebFluxConfig.html).
- Spring Boot 3.5 — [WebFluxAutoConfiguration.EnableWebFluxConfiguration Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/reactive/WebFluxAutoConfiguration.EnableWebFluxConfiguration.html).
- Spring Framework — [WebFlux Config: @EnableWebFlux and WebFluxConfigurer](https://docs.spring.io/spring-framework/reference/web/webflux/config.html).
- Spring Framework — [DelegatingWebFluxConfiguration Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/config/DelegatingWebFluxConfiguration.html).
- Spring Boot — [Common Application Properties: WebFlux and HTTP codec settings](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html).
