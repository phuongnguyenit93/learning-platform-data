# WebBindingInitializer và ConfigurableWebBindingInitializer trong Spring Framework

Trong Spring MVC, mỗi lần một request cần chuyển query/form values thành Java objects, framework thường tạo một **`WebDataBinder`**. Binder biết cách gắn giá trị vào JavaBean, chuyển `String` thành `Integer`/enum/date, ghi lại lỗi type conversion và phối hợp với validator. Nếu muốn các binder trong nhiều controller dùng chung một cấu hình, Spring cung cấp hai API quan trọng:

- **`WebBindingInitializer`**: *callback interface* khởi tạo một `WebDataBinder` mới bằng phương thức `initBinder(WebDataBinder binder)`.
- **`ConfigurableWebBindingInitializer`**: implementation sẵn có của interface trên; khai báo chung `ConversionService`, `Validator`, `PropertyEditorRegistrar`, message/error strategies và một số binding policies mà không phải tự viết callback từ đầu.

Ví dụ, ứng dụng muốn tất cả các request binders có chung `FormattingConversionService`/Jakarta Validator và chính sách `declarativeBinding`. Thay vì đặt cùng ba lệnh cấu hình tại hàng chục controller, ứng dụng có thể tạo **một `ConfigurableWebBindingInitializer`**, đưa nó vào Spring MVC infrastructure, rồi dùng `@InitBinder` cho các quy tắc riêng của một form.

**Mục tiêu:** hiểu interface và implementation, vòng đời, điểm cắm với `RequestMappingHandlerAdapter`, khả năng và giới hạn từng setter, cách phối hợp `@InitBinder`, và cách kiểm thử để chắc chắn cấu hình global thực sự được áp dụng. Ví dụ chạy trên **Java 17+ / Spring Boot 3.5.x / Spring Framework 6.2.x / Spring MVC Servlet stack**; Spring WebFlux có điểm kết nối tương tự nhưng dùng một handler adapter khác.

## 1. Vì sao cần khởi tạo binder?

Xét request:

~~~http
POST /catalog/filters HTTP/1.1
Host: localhost:8080
Content-Type: application/x-www-form-urlencoded

code=SKU-7&quantity=2&tier=PREMIUM
~~~

và chữ ký controller:

~~~java
@PostMapping("/catalog/filters")
public Object submit(
        @Valid @ModelAttribute("filter") CatalogFilter form,
        BindingResult errors) {
    // Xử lý sau khi Spring MVC bind và validate.
    return ...;
}
~~~

Đây là **snippet minh họa**; chương trình hoàn chỉnh ở phần 7. Spring sẽ tìm/tạo `CatalogFilter`, tạo binder phù hợp, đọc các request parameter values, chuyển `quantity="2"` thành `Integer 2`, chuyển `tier="PREMIUM"` thành enum `Tier.PREMIUM`, đặt vào object rồi thực thi validation theo `@Valid` nếu có validator.

Nếu binder chưa có đúng converter/formatter, `quantity` hoặc `tier` có thể gây **type mismatch**. Nếu không cấu hình giới hạn field, một client có thể gửi thêm key nhạy cảm trùng setter của object. Nếu không có validator đang hoạt động, annotation `@Min`/`@NotBlank` trên DTO có thể không được kiểm tra theo cách mong đợi.

Đây là ba loại vấn đề khác nhau:

1. **Type conversion:** dữ liệu chuỗi được chuyển thành loại Java nào?
2. **Binding policy:** field nào được phép thay đổi, dùng setter hay truy cập field trực tiếp?
3. **Validation:** khi nào kiểm tra quy tắc, validator nào xử lý và báo lỗi dưới dạng nào?

`WebBindingInitializer` là nơi chuẩn bị những quy tắc **dùng chung** cho binder; nó **không** tự đọc HTTP request hoặc gọi validation trên mọi object.

## 2. API chính xác và vị trí package

### 2.1. `WebBindingInitializer`

Interface nằm tại:

~~~java
org.springframework.web.bind.support.WebBindingInitializer
~~~

Hợp đồng cốt lõi:

~~~java
public interface WebBindingInitializer {
    void initBinder(WebDataBinder binder);
}
~~~

Đoạn trên mô tả chữ ký API, không phải source code cần chép lại vào project. `WebDataBinder` thuộc package `org.springframework.web.bind.WebDataBinder`. Khi Spring MVC tạo binder cho một request/model attribute, infrastructure có thể gọi `initBinder(binder)` để áp dụng cấu hình.

**Những điều interface này KHÔNG làm:**

- Không tự tạo object form hoặc giải mã JSON.
- Không thay thế `@ModelAttribute`, `@RequestParam` hay `@RequestBody`.
- Không tự động chạy `binder.validate()` ngay khi `initBinder` được gọi.
- Không quyết định handler mapping, HTTP status, hay model/view.
- Không có callback riêng nhận toàn bộ request/session mặc định; signature chỉ có **binder**.

Vì vậy, `WebBindingInitializer` thích hợp cho những chính sách binder **không phụ thuộc một request cụ thể**. Nếu cần điều kiện theo một form, controller hoặc request, thường dùng `@InitBinder` thay vì cố nhét mọi logic vào global initializer.

### 2.2. `ConfigurableWebBindingInitializer`

Class nằm tại:

~~~java
org.springframework.web.bind.support.ConfigurableWebBindingInitializer
~~~

Nó **implements `WebBindingInitializer`**, và cấu hình thông qua các setter:

~~~java
ConfigurableWebBindingInitializer initializer =
    new ConfigurableWebBindingInitializer();

initializer.setConversionService(conversionService);
initializer.setValidator(validator);
initializer.setDeclarativeBinding(true);
initializer.setAutoGrowNestedPaths(false);

// Framework hoặc code chủ động sẽ gọi:
initializer.initBinder(binder);
~~~

Đây là **snippet minh họa có biến phụ thuộc** `conversionService`, `validator`, `binder`; chưa phải một main method độc lập. Class này giúp tái sử dụng cấu hình trên nhiều binder; mỗi binder vẫn là một object riêng theo ngữ cảnh binding.

### 2.3. Điểm tích hợp với Spring MVC

Trong Spring MVC Servlet, `RequestMappingHandlerAdapter` có phương thức:

~~~java
void setWebBindingInitializer(
    WebBindingInitializer initializer);
~~~

Tài liệu API mô tả initializer như chính sách khởi tạo **global** cho các `WebDataBinder` do handler adapter dùng. Factory như `DefaultDataBinderFactory` hoặc `InitBinderDataBinderFactory` liên kết initializer với quá trình tạo binder.

Đừng tự gọi `requestMappingHandlerAdapter.setWebBindingInitializer(...)` lên một bean tự khởi tạo bằng `new` rồi mong toàn bộ Spring MVC tự chuyển sang adapter đó. Chỉ khi chỉnh **đúng adapter đang được framework sử dụng** thì mới có tác dụng.

**Với Spring Boot 3.5**, tài liệu chính thức xác nhận: nếu khai báo **một bean kiểu `ConfigurableWebBindingInitializer`**, Boot MVC auto-configuration sẽ sử dụng bean đó. Đây là con đường thực hành ở phần 7.

## 3. Luồng tạo binder: global trước, local sau

Một luồng thường gặp trong Spring MVC:

~~~text
HTTP request
  |
  v
DispatcherServlet
  |
  v
RequestMappingHandlerAdapter
  |
  v
WebDataBinderFactory tạo WebDataBinder
  |
  +--> WebBindingInitializer.initBinder(binder)
  |      (global: validator, conversion, field mode, ...)
  |
  +--> @InitBinder methods có phạm vi áp dụng
  |      (controller / @ControllerAdvice / attribute name)
  |
  v
Resolve @ModelAttribute / @RequestParam / other arguments
  |
  +--> Constructor binding / property binding theo policy
  +--> ConversionService / Formatter / PropertyEditor
  +--> ghi nhận lỗi binding trong BindingResult
  |
  v
@Valid / @Validated nếu được kích hoạt
  |
  +--> lỗi thuộc BindingResult hoặc exception
  |
  v
Controller handler hoặc error handling
~~~

`DefaultDataBinderFactory` nêu rõ việc khởi tạo bổ sung qua `@InitBinder` được thực hiện **sau** global `WebBindingInitializer`. Vì thế có thể coi:

- **Initializer toàn cục** đặt baseline chung.
- **`@InitBinder`** bổ sung hay tùy chỉnh baseline cho một controller, nhóm controller, hoặc tên model attribute cụ thể.
- **Converter/Formatter** trong MVC `FormattingConversionService` có thể được đăng ký qua `WebMvcConfigurer` để các binder cùng sử dụng.

Đây là **thứ tự cấu hình**, không phải bảo đảm mọi setter local “thắng” mọi setter global theo cùng một cách. Chẳng hạn khi bật `declarativeBinding` toàn cục, việc thiết lập `allowedFields` cho form cục bộ cho phép property binding ở phạm vi đó; nhưng dùng cùng một converter/validator hoặc ghi đè property editor còn phụ thuộc cơ chế của từng thuộc tính.

### Một initializer có được gọi cho nhiều binder không?

Có. Cùng cấu hình dùng chung có thể được áp vào nhiều binder mới. Không đặt trạng thái **request-specific mutable** như giá trị user ID hiện tại vào field của initializer singleton, vì nhiều request có thể sử dụng cấu hình đó đồng thời.

### Binder có tồn tại mãi không?

Không nên xem `WebDataBinder` như một “service singleton” giữ dữ liệu. Binder được tạo để xử lý một target/request context, chứa `BindingResult` và trạng thái binding tương ứng. Global initializer thường dùng chung, **binder và kết quả binding thuộc từng lần xử lý**.

## 4. Các tuỳ chọn của `ConfigurableWebBindingInitializer`

Spring Framework 6.2 cung cấp nhiều setter; nên hiểu tác dụng và rủi ro trước khi bật trên toàn ứng dụng.

| API | Ý nghĩa | Khi nào dùng / cảnh báo |
|---|---|---|
| `setConversionService(ConversionService)` | Cung cấp converter/formatter engine cho binder | Dùng **MVC conversion service** đã có thay vì thay bằng instance rỗng |
| `setValidator(Validator)` | Gắn Spring `org.springframework.validation.Validator` cho binder | Không tự kích hoạt validation nếu handler không yêu cầu hoặc code không gọi `validate()` |
| `setPropertyEditorRegistrar(...)` | Đăng ký một `PropertyEditorRegistrar` trên binder | Hữu ích cho editor cũ/đặc thù; chú ý tính stateful |
| `setPropertyEditorRegistrars(...)` | Đăng ký nhiều registrars | Dùng khi có nhiều nhóm property editors |
| `setDirectFieldAccess(boolean)` | Chuyển sang truy cập field trực tiếp thay vì JavaBeans property access | Cân nhắc tính đóng gói, field private, tính nhất quán và nested paths |
| `setAutoGrowNestedPaths(boolean)` | Cho phép tự khởi tạo nested path null và auto-grow collection theo binder | Có hệ quả tài nguyên/an toàn; chỉ áp dụng cho bean property access phù hợp |
| `setDeclarativeBinding(boolean)` | Bật chế độ chỉ bind những field được dự định bind | Với Spring 6.1+; property binding không chạy mặc định nếu không khai báo allowed fields |
| `setMessageCodesResolver(MessageCodesResolver)` | Tùy chỉnh cách xây message codes của errors | Tác động error code resolution, không thay đổi logic constraint |
| `setBindingErrorProcessor(BindingErrorProcessor)` | Tùy chỉnh xử lý required field/property access errors | Thay đổi cách ghi lỗi binding, không phải validator thay thế |
| `initBinder(WebDataBinder)` | Áp toàn bộ cấu hình vào binder được đưa vào | Được framework/factory gọi, không phải API bind request |

Các getter như `getConversionService()`, `getValidator()`, `getMessageCodesResolver()`, `getBindingErrorProcessor()` và các getter cấu hình giúp kiểm tra initializer đã được chuẩn bị đúng.

### `setConversionService` không thay thế `@RequestBody` JSON

Converter/formatter của `ConversionService` chủ yếu xử lý chuyển đổi kiểu khi binding request parameters, URI variables và form properties. JSON body với `@RequestBody` thường được đọc bằng **`HttpMessageConverter`** (ví dụ Jackson), không phải bằng một `Converter<String,Dto>` của data binder.

Có thể có validation áp dụng cho DTO từ `@RequestBody`; đó là bước khác với việc chuyển JSON text bằng `ConversionService`. Đừng gắn Jackson và `FormattingConversionService` thành một cơ chế duy nhất.

### `setValidator` nhận loại nào?

Chữ ký dùng **Spring Validator**:

~~~java
org.springframework.validation.Validator
~~~

Một `LocalValidatorFactoryBean` có thể đóng vai trò adapter tích hợp Jakarta Validation và triển khai những interface liên quan. Đừng truyền bừa `jakarta.validation.Validator` vào setter nếu object không triển khai Spring `Validator`; hai interface có vai trò và chữ ký method khác nhau.

Trong Spring Boot MVC, các bean `mvcValidator` và `mvcConversionService` đã được framework cấu hình. Khi tạo initializer tùy chỉnh, cần **giữ lại hai thành phần này** nếu không muốn vô tình làm mất conversion/validation mặc định.

### `setAutoGrowNestedPaths` và collection

Ví dụ form có `customer.address.city`, trong đó `address` ban đầu null. Với auto-grow, binder có thể tạo nested object phù hợp khi có constructor khả dụng. Tuy nhiên nó không thể tạo được mọi kiểu tùy ý, và collection growth còn chịu các giới hạn trong DataBinder (ví dụ `autoGrowCollectionLimit`).

Nếu ứng dụng nhận request không tin cậy, đừng coi auto-grow là một tính năng vô hại: nested property paths/index có thể khiến object graph hoặc collection tăng ngoài ý muốn. Hạn chế DTO, allowed fields và giới hạn kích thước request.

### `setDirectFieldAccess`

Mặc định binder truy cập JavaBean properties, thường qua getter/setter. `setDirectFieldAccess(true)` cho phép binder tiếp cận fields trực tiếp theo cơ chế của Spring, giúp một số object thiếu setter được bind, nhưng có thể bỏ qua logic encapsulation của setter.

**Không dùng direct-field access để “bẻ khóa” entity/domain class** chứa trạng thái không được phép sửa. Chọn request DTO đúng phạm vi và constructor binding khi phù hợp.

### `setDeclarativeBinding`

Khi bật:

~~~java
initializer.setDeclarativeBinding(true);
~~~

binder ưu tiên constructor binding và **không tự property-bind mọi writable property** nữa. Property binding chỉ được mở cho trường đã khai báo rõ như qua `binder.setAllowedFields("code", "quantity")`.

Chế độ này đặc biệt có ý nghĩa để tránh **mass assignment/over-posting**. Tuy nhiên, nếu áp dụng toàn cục cho một dự án đang dùng nhiều mutable JavaBeans với setters và không có allowed-fields lists, các form có thể đột ngột không nhận giá trị như trước. Phải rà soát các handler/model trước khi bật.

## 5. Phân biệt ba điểm cấu hình: initializer, WebMvcConfigurer và @InitBinder

| Cơ chế | Phạm vi chính | Ví dụ |
|---|---|---|
| `WebBindingInitializer` | Callback baseline cho binder mới của adapter | Quy định truy cập field, policy bind, editor, validation setup |
| `ConfigurableWebBindingInitializer` | Implementation declarative của callback dùng chung | Gắn MVC conversion service, validator, declarative binding |
| `WebMvcConfigurer.addFormatters` | Đăng ký converter/formatter dùng chung cho Spring MVC | Converter cho enum alias, value object hoặc date formatting |
| `@ControllerAdvice @InitBinder` | Các controller được advice áp dụng; có thể chọn scope | Allowed fields/PropertyEditor dùng chung một nhóm controllers |
| `@Controller @InitBinder("form")` | Một controller hoặc một model attribute có tên `form` | Allowed fields cho đúng một form |
| `@ModelAttribute` | Nhận/tạo model attribute, khởi động binding theo resolver | Controller nhận object đã bind |
| `@Valid` / `@Validated` | Yêu cầu validation sau binding ở điểm được hỗ trợ | Kiểm tra các constraints trên DTO |
| `BindingResult` | Chứa binding/validation errors cho một object | Handler tự quyết định phản hồi lỗi |

Tập trung vào **trách nhiệm**:

- **Thêm một converter mới:** thông thường dùng `WebMvcConfigurer.addFormatters`; không cần thay cả initializer.
- **Gắn allowed-fields chỉ cho một form:** `@InitBinder("filter")` rõ ràng và ít ảnh hưởng hơn.
- **Muốn mọi binder có chung policy nền:** cân nhắc `ConfigurableWebBindingInitializer`.
- **Muốn công cụ đặc thù làm logic không có trong Configurable...:** tự triển khai `WebBindingInitializer`, nhưng phải kết nối đúng với handler adapter của web stack, đồng thời giữ những tính năng MVC cấu hình sẵn.
- **Muốn kiểm tra business/domain rules:** Bean Validation hoặc service/domain layer, không lạm dụng initializer như “service nghiệp vụ”.

Ví dụ bộ chuyển đổi tùy chỉnh qua `WebMvcConfigurer`:

~~~java
@Configuration
public class ExtraFormatters implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
            String.class,
            ProductCode.class,
            raw -> new ProductCode(raw.strip()));
    }
}
~~~

Đây là đoạn **minh họa**, cần record/class `ProductCode`, imports `@Configuration`, `WebMvcConfigurer`, `FormatterRegistry` phù hợp. Không phải một file độc lập trong project demo. Khi cấu hình có `@Bean ConfigurableWebBindingInitializer`, hãy tái sử dụng `mvcConversionService` để converter đăng ký qua `WebMvcConfigurer` vẫn được sử dụng.

## 6. Ví dụ triển khai trực tiếp bằng interface

Nếu chỉ muốn hiểu hoạt động của contract, có thể khởi tạo binder bằng Java code sử dụng Spring API:

~~~java
WebBindingInitializer global = initializer;

CatalogFilter form = new CatalogFilter();
WebDataBinder binder = new WebDataBinder(form, "filter");

global.initBinder(binder); // Chỉ chuẩn bị cấu hình.
binder.setAllowedFields("code", "quantity", "tier");

MutablePropertyValues input = new MutablePropertyValues();
input.add("code", "SKU-7");
input.add("quantity", "2");
input.add("tier", "PREMIUM");
binder.bind(input);          // Gắn giá trị, thực hiện conversion.
binder.validate();           // Chạy validator đã gắn, nếu phù hợp.

BindingResult errors = binder.getBindingResult();
~~~

Snippet trên cần `initializer` đã tạo, `CatalogFilter` từ phần 7 và imports:

~~~java
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.support.WebBindingInitializer;
~~~

Phần này **không dùng HTTP request**, nhưng minh họa chính xác trách nhiệm riêng:

1. `initBinder` **khởi tạo chính sách**, không bind giá trị.
2. `binder.bind(...)` mới áp property values.
3. `binder.validate()` mới chủ động yêu cầu Spring validator kiểm tra object.
4. `getBindingResult()` mới cung cấp lỗi để đọc, kiểm thử và báo cáo.

Trong MVC thật, resolver/factory tự tạo binder, gọi initializer, bind và kích hoạt validation khi handler argument có annotation phù hợp. Đừng tự tạo một binder mới trong mỗi controller chỉ để thay thế framework.

### Custom implementation của `WebBindingInitializer`

Interface có thể được tự triển khai:

~~~java
public final class ExplicitInitializer
        implements WebBindingInitializer {

    @Override
    public void initBinder(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
        binder.setAutoGrowNestedPaths(false);
    }
}
~~~

Đây là **class minh họa riêng**, cần imports và lưu thành `ExplicitInitializer.java` nếu dùng. Một implementation thuần như vậy **chưa tự gắn** MVC `ConversionService` hay `Validator`. Nếu thay toàn bộ initializer mặc định bằng instance này mà bỏ qua những thành phần có sẵn, type conversion/validation có thể bị ảnh hưởng.

Trong Spring Boot 3.5, con đường tự động được ghi trong tài liệu là khai báo bean **`ConfigurableWebBindingInitializer`**. Nếu muốn custom arbitrary `WebBindingInitializer`, cần có cách tích hợp phù hợp với đúng `RequestMappingHandlerAdapter`; không giả định chỉ cần `@Component` trên interface implementation là Boot sẽ tự lấy nó thay cho configurable initializer.

## 7. Ứng dụng Spring Boot 3.5 hoàn chỉnh: global initializer + local allowlist

Ta xây một form lọc sản phẩm với ba trường được người dùng phép gửi: `code`, `quantity`, `tier`. Trong DTO cố tình có thêm `admin` để chứng minh **một setter tồn tại không có nghĩa request được phép ghi vào nó**.

Ứng dụng sử dụng:

- `ConfigurableWebBindingInitializer` bean để đặt **global declarative binding policy** và giữ `mvcConversionService`/`mvcValidator`.
- `@InitBinder("filter")` trong controller để khai báo **allowed fields** cho form này.
- `@Valid @ModelAttribute("filter")` và `BindingResult` để kiểm tra constraint và type conversion.
- `MockMvc` để kiểm chứng **binder được tạo bởi Spring MVC thật**, không phải chỉ chạy Java setter.

Các file đặt trong package `com.example.binderinit`. Project được tạo từ Spring Initializr với Java 17+ và Spring Boot **3.5.x**.

### 7.1. Dependencies Gradle

Trong project đã có Spring Boot Gradle plugin và version management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Starter Web dùng Spring MVC Servlet stack; starter Validation cung cấp Jakarta provider. `spring-boot-starter-test` phục vụ JUnit/MockMvc. Không cần Spring Data hay database. Không dùng `javac` thuần chỉ với JDK, vì code import Spring/Jakarta.

### 7.2. `BinderDemoApplication.java`

`src/main/java/com/example/binderinit/BinderDemoApplication.java`:

~~~java
package com.example.binderinit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BinderDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BinderDemoApplication.class, args);
    }
}
~~~

### 7.3. `GlobalBinderConfiguration.java`

`src/main/java/com/example/binderinit/GlobalBinderConfiguration.java`:

~~~java
package com.example.binderinit;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.format.support.FormattingConversionService;
import org.springframework.validation.Validator;
import org.springframework.web.bind.support.ConfigurableWebBindingInitializer;

@Configuration(proxyBeanMethods = false)
public class GlobalBinderConfiguration {

    @Bean
    public ConfigurableWebBindingInitializer
            configurableWebBindingInitializer(
            @Qualifier("mvcConversionService")
            FormattingConversionService mvcConversionService,
            @Qualifier("mvcValidator")
            Validator mvcValidator) {

        ConfigurableWebBindingInitializer initializer =
            new ConfigurableWebBindingInitializer();

        // Giữ các thành phần MVC do Spring Boot cấu hình.
        initializer.setConversionService(mvcConversionService);
        initializer.setValidator(mvcValidator);

        // Chặn property binding không được khai báo rõ.
        initializer.setDeclarativeBinding(true);

        return initializer;
    }
}
~~~

**Điểm cần hiểu:**

- Boot 3.5 MVC auto-configuration nhận biết bean kiểu `ConfigurableWebBindingInitializer` và dùng nó để khởi tạo những binder của MVC. **Đây không chỉ là bean “để đó”, mà là điểm mở rộng được Spring Boot tài liệu hóa.**
- Việc inject bean có qualifier `mvcConversionService` và `mvcValidator` giúp giữ conversion/validation mà Spring MVC đã chuẩn bị. Nếu tự tạo `new DefaultConversionService()` và quên validator, ứng dụng có thể mất formatter/custom converter và validation đã cấu hình trước.
- `setDeclarativeBinding(true)` là chính sách **global**. Nếu không có allowed-fields list ở controller, mutable JavaBean có constructor rỗng sẽ không property-bind như trước.
- Không thêm `@EnableWebMvc` vào Boot demo: annotation đó có thể khiến Boot MVC auto-configuration bị thay thế, làm cách tích hợp thay đổi.
- Chỉ nên có một cấu hình initializer mục đích rõ ràng; đừng tạo nhiều bean cùng kiểu và hy vọng Spring chọn ngẫu nhiên một cái.

Nếu không cần global declarative binding, **đừng tạo bean này chỉ để cho giống mẫu**. Spring Boot đã chuẩn bị binding infrastructure mặc định. Mẫu đang chủ ý chứng minh global customization.

### 7.4. `CatalogFilter.java`

`src/main/java/com/example/binderinit/CatalogFilter.java`:

~~~java
package com.example.binderinit;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class CatalogFilter {

    public enum Tier {
        BASIC, PREMIUM
    }

    @NotBlank
    private String code;

    @NotNull
    @Min(1)
    private Integer quantity;

    private Tier tier = Tier.BASIC;

    // Chỉ để minh họa field không được phép nhận từ HTTP.
    private boolean admin;

    public CatalogFilter() {
    }

    public String getCode() {
        return code;
    }

    public void setCode(String code) {
        this.code = code;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }

    public Tier getTier() {
        return tier;
    }

    public void setTier(Tier tier) {
        this.tier = tier;
    }

    public boolean isAdmin() {
        return admin;
    }

    public void setAdmin(boolean admin) {
        this.admin = admin;
    }
}
~~~

Vì `tier` là enum, MVC ConversionService chuyển `"PREMIUM"` thành `Tier.PREMIUM` theo default enum conversion. String `"premium"` không đương nhiên được chấp nhận trong mọi cấu hình; muốn alias/case-insensitive thì thêm converter tường minh.

`admin` là **một setter nguy hiểm có chủ ý trong DTO demo**. Trong code production, tốt nhất **không đưa trường quyền hạn vào request DTO**. Mẫu này dùng nó để chứng minh allowlist hoạt động, không khuyến khích design DTO có admin flag.

### 7.5. `CatalogController.java`

`src/main/java/com/example/binderinit/CatalogController.java`:

~~~java
package com.example.binderinit;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/catalog")
public class CatalogController {

    @InitBinder("filter")
    public void configureFilter(WebDataBinder binder) {
        binder.setAllowedFields("code", "quantity", "tier");
    }

    @PostMapping(
        path = "/filters",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<FilterResult> filter(
            @Valid @ModelAttribute("filter") CatalogFilter form,
            BindingResult errors) {

        int errorCount = errors.getErrorCount();
        int suppressedCount = errors.getSuppressedFields().length;

        if (errorCount > 0 || suppressedCount > 0) {
            return ResponseEntity.badRequest().body(
                new FilterResult(
                    false, null, null, null, false,
                    errorCount, suppressedCount));
        }

        return ResponseEntity.ok(
            new FilterResult(
                true,
                form.getCode(),
                form.getQuantity(),
                form.getTier().name(),
                form.isAdmin(),
                0,
                0));
    }

    public record FilterResult(
        boolean accepted,
        String code,
        Integer quantity,
        String tier,
        boolean admin,
        int errorCount,
        int suppressedCount
    ) {
    }
}
~~~

Controller cho thấy **phân công rõ**:

1. `@InitBinder("filter")` chỉ áp dụng cho model attribute tên `filter`, đặt allowed fields `code`, `quantity` và `tier`. Nó **không** thay đổi global ConversionService/Validator.
2. Global `setDeclarativeBinding(true)` khiến property binding chỉ được mở khi có allowed-fields list thích hợp; local `setAllowedFields(...)` mở cho ba field.
3. `@ModelAttribute("filter")` tạo/gắn form từ request parameters (ở đây POST `application/x-www-form-urlencoded`).
4. `@Valid` kích hoạt Jakarta Validation sau binding; `BindingResult` đặt **ngay sau** object.
5. Nếu có constraint/type mismatch errors **hoặc** suppressed fields, controller trả HTTP 400. Suppressed fields không mặc nhiên là Bean Validation errors, nên cần kiểm tra `getSuppressedFields()` riêng.
6. Khi hợp lệ, controller trả JSON để tiện quan sát; không cần template engine.

**Lưu ý bảo mật:** Không trả rejected values hay thông tin nhạy cảm trong error response demo. Nếu có request `admin=true`, binder suppresses field `admin`; controller phản hồi 400. `admin` trên object vẫn là `false` trong trường hợp này.

### 7.6. Chạy và quan sát

Trên Unix/macOS:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu cổng 8080 đang rảnh và không đổi `server.port`, gọi form hợp lệ:

~~~bash
curl -i -X POST "http://localhost:8080/catalog/filters" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "code=SKU-7" \
  --data-urlencode "quantity=2" \
  --data-urlencode "tier=PREMIUM"
~~~

Kỳ vọng **HTTP 200 OK**, JSON tương đương:

~~~json
{
  "accepted": true,
  "code": "SKU-7",
  "quantity": 2,
  "tier": "PREMIUM",
  "admin": false,
  "errorCount": 0,
  "suppressedCount": 0
}
~~~

Nếu không có `tier`, field giữ giá trị mặc định `BASIC` của JavaBean mới.

Thử input sai constraints:

~~~bash
curl -i -X POST "http://localhost:8080/catalog/filters" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "code=" \
  --data-urlencode "quantity=0"
~~~

Kỳ vọng **HTTP 400**, JSON:

~~~json
{
  "accepted": false,
  "code": null,
  "quantity": null,
  "tier": null,
  "admin": false,
  "errorCount": 2,
  "suppressedCount": 0
}
~~~

Hai lỗi là `@NotBlank` với `code=""` và `@Min(1)` với `quantity=0`. `@NotNull` của `quantity` không vi phạm vì 0 là một Integer không null.

Thử ghi field không được phép:

~~~bash
curl -i -X POST "http://localhost:8080/catalog/filters" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "code=SKU-7" \
  --data-urlencode "quantity=2" \
  --data-urlencode "admin=true"
~~~

Kỳ vọng **HTTP 400** với `accepted=false`, `errorCount=0` và `suppressedCount=1`. `admin` bị từ chối tại binding layer và không được chuyển thành quyền admin. Ứng dụng cố ý xem một request chứa field ngoài allowlist là lỗi thay vì bỏ qua im lặng.

Thử type mismatch:

~~~bash
curl -i -X POST "http://localhost:8080/catalog/filters" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "code=SKU-7" \
  --data-urlencode "quantity=abc"
~~~

Kỳ vọng **HTTP 400** vì `quantity` không thể chuyển thành `Integer`; loại lỗi gốc là binding/conversion, không phải một phép so sánh `@Min(1)` trên số hợp lệ. Số `errorCount` khi kết hợp type mismatch và Bean Validation phụ thuộc đường xử lý/DTO, nên test chỉ nên cố định status hoặc kiểm tra mã lỗi phù hợp nếu thiết kế riêng error contract.

**Đây là chương trình Spring Boot**, không phải chương trình Java dùng `main` và tự gọi `WebBindingInitializer.initBinder`. Lệnh chạy là Gradle wrapper với Spring Boot plugin; HTTP server và Spring MVC tự thực hiện binding.

## 8. Integration test: chứng minh initializer được Spring MVC sử dụng

Test nên xác nhận không chỉ response HTTP mà còn **handler adapter thực sự nhận bean initializer**. Với `spring-boot-starter-test` đã có trong dependency, tạo:

`src/test/java/com/example/binderinit/CatalogControllerTest.java`

~~~java
package com.example.binderinit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.support.ConfigurableWebBindingInitializer;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerAdapter;

import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CatalogControllerTest {

    @Autowired
    private MockMvc mvc;

    @Autowired
    private ConfigurableWebBindingInitializer initializer;

    @Autowired
    private RequestMappingHandlerAdapter adapter;

    @Test
    void mvcUsesOurGlobalInitializer() {
        assertSame(initializer, adapter.getWebBindingInitializer());
        assertTrue(initializer.isDeclarativeBinding());
    }

    @Test
    void allowsDeclaredFieldsAndConvertsTypes()
            throws Exception {
        mvc.perform(post("/catalog/filters")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("code", "SKU-7")
                .param("quantity", "2")
                .param("tier", "PREMIUM"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.accepted").value(true))
            .andExpect(jsonPath("$.code").value("SKU-7"))
            .andExpect(jsonPath("$.quantity").value(2))
            .andExpect(jsonPath("$.tier").value("PREMIUM"))
            .andExpect(jsonPath("$.admin").value(false))
            .andExpect(jsonPath("$.errorCount").value(0))
            .andExpect(jsonPath("$.suppressedCount").value(0));
    }

    @Test
    void validatorRunsOnInvalidForm()
            throws Exception {
        mvc.perform(post("/catalog/filters")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("code", "")
                .param("quantity", "0"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.accepted").value(false))
            .andExpect(jsonPath("$.errorCount").value(2))
            .andExpect(jsonPath("$.suppressedCount").value(0));
    }

    @Test
    void blocksUnexpectedAdminField() throws Exception {
        mvc.perform(post("/catalog/filters")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("code", "SKU-7")
                .param("quantity", "2")
                .param("admin", "true"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errorCount").value(0))
            .andExpect(jsonPath("$.suppressedCount").value(1));
    }

    @Test
    void conversionFailureIsNotAccepted() throws Exception {
        mvc.perform(post("/catalog/filters")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("code", "SKU-7")
                .param("quantity", "not-a-number"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.accepted").value(false));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Windows:

~~~powershell
.\gradlew.bat test
~~~

Với Spring Boot 3.5.x / Spring 6.2.x, Web/Validation starters và không có cấu hình MVC khác can thiệp, năm test kỳ vọng **PASS**.

Đặc biệt, test đầu có giá trị lớn: `assertSame(initializer, adapter.getWebBindingInitializer())` xác minh **bean được gắn vào adapter thật**, chứ không chỉ chứng minh bean đã tồn tại trong ApplicationContext. Nếu test này thất bại, các test còn lại có thể vẫn chạy do cấu hình mặc định nhưng **không chứng minh** global policy mong muốn.

Nếu ứng dụng thật có Spring Security/CSRF, MockMvc POST cần test security setup thích hợp; demo chỉ dùng Web + Validation.

## 9. Sử dụng `PropertyEditorRegistrar` khi cần

`ConfigurableWebBindingInitializer` còn có khả năng đăng ký editor:

~~~java
initializer.setPropertyEditorRegistrar(registry -> {
    registry.registerCustomEditor(
        java.time.YearMonth.class,
        new java.beans.PropertyEditorSupport() {
            @Override
            public void setAsText(String text) {
                setValue(java.time.YearMonth.parse(text));
            }
        });
});
~~~

Đây là **snippet minh họa** nằm trong nơi đang cấu hình `initializer`; `registry` thuộc interface `PropertyEditorRegistry`. Hàm `setPropertyEditorRegistrar` nhận một registrar để đăng ký editor trên mỗi binder. `PropertyEditorSupport` ở đây được tạo **mới mỗi lần registrar được gọi**, tránh chia sẻ một instance editor stateful trên nhiều request.

Tuy nhiên, nếu yêu cầu là chuyển chuỗi sang `YearMonth` cho nhiều MVC handlers, một `Converter<String,YearMonth>` hoặc `Formatter<YearMonth>` được đăng ký qua `WebMvcConfigurer.addFormatters` thường là lựa chọn đơn giản, dễ kiểm thử và có semantics rõ hơn.

**Không** giữ một `PropertyEditorSupport` duy nhất trong field singleton rồi register lại cho mọi binder: property editor có trạng thái chuyển đổi, có thể phát sinh lỗi khi dùng chung giữa nhiều requests/threads.

## 10. MessageCodesResolver và BindingErrorProcessor

Hai tùy chọn nâng cao có thể gây nhầm với Bean Validation:

### `MessageCodesResolver`

Nó quyết định **mã thông báo lỗi có thể được dịch**, không quyết định input đúng hay sai. Ví dụ một field `quantity` sai kiểu có thể dẫn đến các message codes khác nhau theo object/field/type.

~~~java
initializer.setMessageCodesResolver(
    new org.springframework.validation.DefaultMessageCodesResolver());
~~~

Đây là snippet đặt trong nơi có biến `initializer`. Tùy chỉnh mã lỗi có thể hữu ích cho i18n/UI, nhưng không thay thế `MessageSource` và không làm `@Min(1)` có hiệu lực nếu chưa có validator.

### `BindingErrorProcessor`

Nó quy định cách xử lý các sự kiện lỗi binding như required fields hoặc `PropertyAccessException` để đưa vào `BindingResult`.

~~~java
initializer.setBindingErrorProcessor(
    new org.springframework.validation.DefaultBindingErrorProcessor());
~~~

Đây là snippet sử dụng strategy mặc định của Spring. Chỉ thay processor khi thật sự cần error handling đặc biệt; để sửa một converter thiếu hoặc một DTO sai thiết kế, nên sửa nguyên nhân thay vì che giấu lỗi qua processor tùy chỉnh.

Đừng lẫn ba trách nhiệm:

| Thành phần | Vai trò |
|---|---|
| `BindingErrorProcessor` | Đưa lỗi property binding vào error representation |
| `MessageCodesResolver` | Sinh mã lỗi có thể dùng để nội suy thông báo |
| `Validator` | Đánh giá constraint/validation logic khi được yêu cầu |

## 11. Toàn cục không có nghĩa là mọi controller phải giống nhau

### Áp dụng global baseline

Một `ConfigurableWebBindingInitializer` có thể gắn conversion service và validator dùng chung. Đây là cấu hình nền cho những binder mà adapter tạo ra.

### Tùy chỉnh theo controller

`@InitBinder` trong `@Controller` có thể đăng ký property editor, allowed fields hoặc binder flags phù hợp với các handlers ở controller đó.

~~~java
@InitBinder("profileForm")
void configureProfileBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "timezone");
}
~~~

Đây là snippet minh họa, không thuộc controller demo. Chỉ áp dụng cho attribute `profileForm`. Một form khác ở controller khác có thể có danh sách allowed fields riêng.

### Tùy chỉnh cho nhóm controllers

`@ControllerAdvice` có thể chứa `@InitBinder` và giới hạn đối tượng áp dụng bằng package/annotation/assignable types. Tùy cách chọn scope, đây là điểm trung gian giữa “tất cả binder” và “chỉ một controller”.

~~~java
@ControllerAdvice(basePackages = "com.example.forms")
public class FormBinderAdvice {

    @InitBinder
    public void configure(WebDataBinder binder) {
        binder.setAutoGrowNestedPaths(false);
    }
}
~~~

Đây là class minh họa riêng; cần imports tương ứng. Không thêm cùng một advice vào demo ở phần 7 nếu chưa muốn thay đổi nested path policy.

### Tùy chỉnh ConversionService

`WebMvcConfigurer.addFormatters` bổ sung converters/formatters vào MVC ConversionService thay vì thay toàn bộ MVC infrastructure. Với một logic chuyển đổi kiểu mới, đây thường là điểm mở rộng **ưu tiên**.

## 12. Các bẫy thiết kế và bảo mật

### Bẫy 1 — Tạo initializer mới nhưng bỏ validator

~~~java
@Bean
ConfigurableWebBindingInitializer unsafeInitializer() {
    return new ConfigurableWebBindingInitializer();
}
~~~

Đây là **phản ví dụ** khi ứng dụng mong giữ đủ validation/conversion mặc định. Một initializer rỗng không nhất thiết phản ánh những giá trị mà Boot mặc định gắn vào adapter. Nếu Boot dùng bean này thay cho initializer mặc định, kết quả có thể ảnh hưởng validation/type conversion. Hãy inject **`mvcConversionService`** và **`mvcValidator`** đã cấu hình, hoặc cân nhắc không tạo bean tùy chỉnh.

### Bẫy 2 — Dùng global `setDirectFieldAccess(true)` để bind domain entity

Nó có thể bỏ qua setter logic và mở rộng surface sửa dữ liệu. Vẫn cần DTO giới hạn input, validation và authorization; không bao giờ coi field access là thay thế thiết kế bảo mật.

### Bẫy 3 — Áp `setDeclarativeBinding(true)` nhưng quên allowed fields

Mutable JavaBean chỉ có no-arg constructor/setters có thể không nhận request parameter values như trước. Các form sẽ trông như “bị reset” hoặc default values không đổi. Nếu muốn constructor-only, hãy thiết kế immutable DTO đúng mục đích; nếu cần setter binding, khai báo allowlist theo form.

### Bẫy 4 — Cho client bind trực tiếp entity có admin/price/owner fields

Mass assignment là nguy cơ ngay cả khi không có input HTML tương ứng. Client có thể tự gửi key `admin=true`. Dùng DTO riêng và `allowedFields` cho property binding, kiểm tra suppressed fields nếu chính sách yêu cầu, rồi map **chỉ** những trường hợp lệ sang entity sau authorization.

### Bẫy 5 — Cho rằng `setValidator` đồng nghĩa mọi object luôn được validate

`initBinder` chỉ đăng ký validator. Với `@ModelAttribute`, validation thường được kích hoạt khi handler khai báo `@Valid`/`@Validated`; với binder dùng trực tiếp, phải gọi `binder.validate()`. Thiếu annotation/validation call thì constraint có thể không được đánh giá.

### Bẫy 6 — Nhầm global initializer với ApplicationContext-wide ConversionService

`ConversionService` là một thành phần có thể được nhiều subsystem dùng. MVC có bean riêng `mvcConversionService`. Đừng sửa hoặc thay toàn bộ conversion service toàn ứng dụng chỉ để giải quyết một form đặc thù.

### Bẫy 7 — Cấu hình sai web stack

Trong Spring MVC, initializer được dùng bởi `org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerAdapter`. Trong Spring WebFlux có một adapter riêng: `org.springframework.web.reactive.result.method.annotation.RequestMappingHandlerAdapter` cũng có điểm nhận `WebBindingInitializer`. Nhưng **MVC Boot autoconfig customization không tự động đồng nghĩa đã tùy chỉnh WebFlux**. Kiểm tra web stack thực tế.

### Bẫy 8 — Đặt mutable request state vào singleton initializer

Initializer là cấu hình dùng lại; đừng tích trữ rejected values, current username hay bản thân `WebDataBinder` của request trong field chung. Request-level binding data nằm trên binder/BindingResult, còn current-user/context có nơi lưu an toàn riêng.

## 13. Các lỗi phổ biến khi triển khai

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Bean `ConfigurableWebBindingInitializer` có nhưng MVC không dùng | Không phải adapter Boot MVC đang dùng, custom `@EnableWebMvc`, hoặc bean không đúng type/context | Inject `RequestMappingHandlerAdapter`, kiểm tra `getWebBindingInitializer()` |
| Form fields không được gán sau khi bật declarative binding | Chưa khai báo allowed fields, hoặc DTO không có constructor phù hợp | Kiểm tra `setDeclarativeBinding` và `@InitBinder` |
| `@InitBinder("filter")` không chạy với DTO | Tên `@ModelAttribute` thực tế không phải `filter` | Đặt tên attribute tường minh và kiểm tra scope |
| `quantity=abc` không convert | ConversionService thiếu converter hoặc input sai format | Xem `BindingResult.getFieldErrors()` và converter |
| `tier=PREMIUM` không chuyển thành enum | Converter đã bị thay hoặc type không khớp | Dùng `mvcConversionService`, xác nhận enum |
| `@NotBlank` không phát hiện chuỗi rỗng | Chưa có validator hoặc chưa kích hoạt `@Valid` | Kiểm tra starter, `mvcValidator` và annotation |
| Request chứa `admin=true` làm thay đổi object | Không giới hạn property binding hoặc dùng entity trực tiếp | Dùng DTO, `setAllowedFields`, theo dõi suppressed fields |
| `BindingResult` rỗng nhưng HTTP request chứa trường lạ | Suppressed fields không mặc nhiên là validation error | Đọc `getSuppressedFields()` riêng |
| Editor hoạt động thất thường giữa các request | Một instance `PropertyEditor` stateful bị dùng chung | Tạo editor mới trong registrar cho mỗi binder |
| Nested object không auto-grow | `autoGrowNestedPaths=false` hoặc nested type không thể tạo | Kiểm tra policy và DTO constructor/property path |
| Đăng ký converter qua `WebMvcConfigurer` nhưng binder không dùng | Custom initializer gắn conversion service khác | Giữ `mvcConversionService`, kiểm tra adapter configuration |
| JSON `@RequestBody` không dùng converter form tùy chỉnh | Body JSON dùng HTTP message converter | Tùy chỉnh Jackson/message converters đúng điểm |
| Global initializer tác động ngoài ý muốn lên nhiều form | Thiết lập quá rộng, ví dụ declarative/direct field access | Chọn scope hẹp hơn bằng `@InitBinder`/ControllerAdvice |
| Có lỗi validation khi method không có `@Valid` | Method validation trực tiếp hoặc configuration khác | Xem constraint trên handler params và validation path |
| Test tạo `new WebDataBinder` vẫn PASS nhưng HTTP không đổi | Test chưa đi qua Spring MVC adapter/binder factory | Thêm MockMvc integration + test adapter initializer identity |

## 14. Bài tập tự kiểm tra

**1. `WebBindingInitializer` và `ConfigurableWebBindingInitializer` khác nhau ở đâu?**

Cái đầu là **interface callback** chỉ định `initBinder(WebDataBinder)`. Cái sau là **implementation cấu hình sẵn**, áp các setter đã thiết lập vào binder.

**2. Khi nào callback chạy?**

Khi framework tạo/khởi tạo binder qua binder factory/handler adapter được nối với initializer, trước các thao tác bind/validate của request. Nó không chạy vì code chỉ import class.

**3. `initBinder` có gọi Bean Validation không?**

Không. Nó chuẩn bị binder; validation xảy ra khi handler/resolver hoặc code chủ động kích hoạt.

**4. Trong Boot 3.5, muốn global initializer làm việc cần khai báo gì?**

Một `@Bean ConfigurableWebBindingInitializer` được Boot MVC auto-configuration nhận diện. Giữ `mvcConversionService` và `mvcValidator` nếu đang tùy chỉnh từ baseline mặc định.

**5. Vì sao sau `setDeclarativeBinding(true)` form mutable có thể không nhận fields?**

Vì property binding không còn được phép mặc định nếu không có allowed fields. Chuyển sang constructor binding hoặc khai báo `setAllowedFields` phù hợp.

**6. Tại sao controller có `@InitBinder("filter")` vẫn cần global initializer?**

Local binder cho phép tùy chỉnh một attribute, trong khi initializer toàn cục gắn baseline conversion/validation/policy cho những binder liên quan. Hai cấp bổ sung nhau.

**7. `@InitBinder("filter")` có áp vào `@ModelAttribute("profile")` không?**

Không theo tên được chọn; cần đúng target name hoặc một `@InitBinder`/advice rộng hơn.

**8. `BindingResult.getErrorCount()` có đếm trường bị suppress không?**

Không nhất thiết. Suppressed fields có API `getSuppressedFields()` riêng; kiểm tra cả hai nếu muốn từ chối key ngoài allowlist.

**9. Dùng global `setDirectFieldAccess(true)` có giải quyết an toàn mass assignment không?**

Không. Nó thay cách truy cập fields, có thể còn tăng rủi ro nếu bind thẳng domain entity. Hạn chế DTO và allowlist, đồng thời kiểm tra quyền.

**10. Vì sao test nên inject `RequestMappingHandlerAdapter`?**

Để chứng minh initializer được Spring MVC **thật sự sử dụng**, không chỉ có mặt trong ApplicationContext.

## 15. Checklist triển khai

- [ ] Xác nhận ứng dụng đang chạy Spring MVC Servlet và phiên bản Spring/Boot phù hợp.
- [ ] Hiểu `WebBindingInitializer.initBinder(WebDataBinder)` là bước cấu hình, không phải bind/validate.
- [ ] Dùng `ConfigurableWebBindingInitializer` khi cần một baseline dùng chung; chỉ tạo bean khi có nhu cầu rõ.
- [ ] Nếu thay initializer mặc định trong Spring Boot, inject lại `mvcConversionService`/`mvcValidator`.
- [ ] Chọn policy declarative/direct field access/auto-grow cẩn thận; đánh giá ảnh hưởng trên tất cả forms.
- [ ] Dùng `@InitBinder` cho các quy tắc có scope nhỏ, như allowed fields một DTO.
- [ ] Dùng `WebMvcConfigurer.addFormatters` cho converter/formatter phổ biến.
- [ ] Khi bind object từ request, ưu tiên DTO chuyên biệt thay vì domain entity.
- [ ] Kích hoạt `@Valid`/`@Validated` nơi thích hợp và đọc `BindingResult` đúng vị trí.
- [ ] Kiểm tra cả constraint/type mismatch errors lẫn suppressed fields nếu policy yêu cầu.
- [ ] Không tái sử dụng mutable PropertyEditor giữa requests.
- [ ] Kiểm thử bằng MockMvc, đặc biệt verify instance initializer trong actual `RequestMappingHandlerAdapter`.
- [ ] Giữ web stack và MVC configuration nhất quán; không dùng `@EnableWebMvc` khi muốn giữ Boot MVC auto-configuration.
- [ ] Theo dõi converter/validator behavior sau khi nâng phiên bản Spring/Boot.

**Ghi nhớ:** `WebBindingInitializer` là callback **chuẩn bị binder**, còn `ConfigurableWebBindingInitializer` là cách cấu hình **conversion, validation, editors, error strategies và binding policies** dùng chung. Trong Spring Boot MVC, bean `ConfigurableWebBindingInitializer` có thể thay baseline tự động; nên giữ `mvcConversionService`/`mvcValidator` và dùng `@InitBinder` để quy định trường được bind cho từng form. Khởi tạo binder khác với thực hiện bind, và bind khác với validation.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 API — WebBindingInitializer](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/support/WebBindingInitializer.html)
- [Spring Framework 6.2 API — ConfigurableWebBindingInitializer](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/support/ConfigurableWebBindingInitializer.html)
- [Spring Framework 6.2 API — DefaultDataBinderFactory](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/support/DefaultDataBinderFactory.html)
- [Spring Framework 6.2 API — RequestMappingHandlerAdapter](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/RequestMappingHandlerAdapter.html)
- [Spring Framework 6.2 — @InitBinder và binding security](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework 6.2 — Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html)
- [Spring Framework 6.2 — Data Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation/data-binding.html)
- [Spring Boot 3.5 — Servlet Web Applications, ConfigurableWebBindingInitializer](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
