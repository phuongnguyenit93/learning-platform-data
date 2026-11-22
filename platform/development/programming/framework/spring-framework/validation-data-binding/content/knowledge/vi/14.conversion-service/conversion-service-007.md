# Tích hợp ConversionService với DataBinder và BeanFactory trong Spring Framework

## 1. Mục tiêu: dùng chung một cơ chế chuyển đổi kiểu ở hai tầng

Trong ứng dụng Spring, chuỗi đầu vào thường cần được chuyển thành kiểu Java trước khi gán vào object. Ví dụ `"usd"` cần trở thành `CurrencyCode("USD")`; `"21"` trở thành `Integer.valueOf(21)`; hoặc một chuỗi ngày trở thành `LocalDate`.

**`ConversionService`** là API chuyển đổi kiểu thống nhất của Spring. Nó tách logic chuyển đổi khỏi nơi gọi, cho phép đăng ký các bộ chuyển đổi có kiểu rõ ràng và dùng lại chúng ở nhiều ngữ cảnh. Chủ đề này tập trung vào hai nơi tích hợp:

- **`BeanFactory` / `ApplicationContext`:** chuyển đổi giá trị cấu hình bean, property value hoặc constructor argument trong quá trình container tạo bean.
- **`DataBinder` / `WebDataBinder`:** chuyển đổi dữ liệu form/request vào object đích, đồng thời phối hợp với property binding, constructor binding và `BindingResult`.

Cùng một `ConversionService` có thể được gắn vào cả hai nơi, nhưng mỗi nơi vẫn cần được cấu hình đúng. Việc đăng ký một `Converter` vào một instance không có nghĩa mọi `BeanFactory` và mọi `DataBinder` ở ứng dụng tự động nhìn thấy instance đó.

Ví dụ xuyên suốt dùng kiểu `CurrencyCode`:

```text
" usd "
   |
   v
Converter<String, CurrencyCode>
   |
   +-------------------------------+
   |                               |
   v                               v
BeanFactory                    DataBinder
bean definition                form input
   |                               |
   v                               v
PaymentSettings.currency       PaymentForm.currency
   |                               |
   +---------- CurrencyCode("USD")+
```

## 2. Các thành phần chính và trách nhiệm

| Thành phần | Trách nhiệm | Điểm tích hợp |
| --- | --- | --- |
| `Converter<S,T>` | Chuyển một kiểu nguồn sang một kiểu đích | Được đăng ký với `ConverterRegistry` |
| `ConverterFactory<S,R>` | Tạo converter cho nhiều kiểu đích thuộc một hierarchy | `ConversionService` |
| `GenericConverter` | Chuyển đổi dựa vào cặp `TypeDescriptor` nguồn/đích, hỗ trợ kiểu phức tạp | `ConversionService` |
| `ConversionService` | API tra cứu khả năng và thực thi chuyển đổi | BeanFactory, DataBinder, các thành phần Spring |
| `ConverterRegistry` | SPI đăng ký/bỏ đăng ký converter | Ví dụ `DefaultConversionService` triển khai |
| `TypeDescriptor` | Mô tả kiểu đầy đủ hơn `Class`, gồm generic và annotation | Chuyển đổi collection, array, Map, property |
| `ConfigurableBeanFactory` | Cho phép gắn ConversionService để convert property/constructor values | Bean creation |
| `DataBinder` | Bind dữ liệu vào một target và ghi lỗi binding | Data binding |
| `WebDataBinder` | Binder chuyên cho web, mở rộng `DataBinder` | Spring MVC/WebFlux binding |

Hai lời gọi thường gặp:

```java
beanFactory.setConversionService(conversionService);
binder.setConversionService(conversionService);
```

Cả hai đều nhận cùng kiểu API `ConversionService`, song cấu hình lên **hai object quản lý khác nhau**. `ConfigurableBeanFactory.setConversionService` quy định chuyển đổi khi bean factory resolve các giá trị cấu hình. `DataBinder.setConversionService` quy định service mà binder dùng khi bind một target.

Không nhầm `ConversionService` với `PropertyEditor`:

- `PropertyEditor` là API JavaBeans có state, thường xử lý dữ liệu text qua `setAsText`/`getAsText`.
- `Converter` là API Spring có kiểu nguồn/đích rõ ràng, thường stateless.
- Spring vẫn hỗ trợ PropertyEditor; khi không có `ConversionService` phù hợp, hệ thống có thể dùng cơ chế editor truyền thống.
- Không cần triển khai cả hai cho cùng một phép chuyển đổi nếu một converter đã giải quyết đầy đủ nhu cầu.

## 3. Viết một Converter dùng ở cả BeanFactory và DataBinder

### 3.1. Kiểu đích

```java
public record CurrencyCode(String value) {}
```

Record này diễn tả một value object nhỏ. Nó không tự chuyển chuỗi thành mã tiền tệ; việc đó thuộc converter.

### 3.2. Converter

```java
import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

public final class StringToCurrencyCodeConverter
        implements Converter<String, CurrencyCode> {

    @Override
    public CurrencyCode convert(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException(
                "Currency code must not be blank"
            );
        }

        String normalized =
            source.strip().toUpperCase(Locale.ROOT);

        if (!normalized.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                "Currency code must contain three letters"
            );
        }

        return new CurrencyCode(normalized);
    }
}
```

Đây là lớp converter có thể dùng độc lập sau khi thêm đúng imports và record `CurrencyCode`. Logic:

1. Từ chối chuỗi null/rỗng/blank theo hợp đồng ví dụ.
2. Dùng `strip()` để loại khoảng trắng ở hai đầu.
3. Dùng `Locale.ROOT` để chuẩn hóa chữ hoa ổn định, không phụ thuộc locale mặc định của máy.
4. Kiểm tra đúng ba ký tự ASCII A–Z.
5. Trả một `CurrencyCode` mới.

`Converter.convert` được gọi với source không null theo contract của Spring ConversionService; tùy chính sách null/empty của luồng gọi, converter có thể không được gọi cho null. Kiểm tra rỗng trong ví dụ giúp diễn tả rõ quy tắc, nhưng không phải một validator toàn diện về danh sách tiền tệ ISO thực. Nếu cần mã tiền tệ hợp lệ theo danh mục, phải kiểm tra với tập mã được sản phẩm chấp nhận.

**Converter nên stateless và thread-safe.** `ConversionService` được thiết kế để được cấu hình lúc khởi động rồi chia sẻ giữa nhiều thread. Không giữ request state, mutable buffer dùng chung hoặc user-specific data trong converter.

## 4. Tạo và đăng ký ConversionService

### 4.1. Dùng `DefaultConversionService` trong Java

```java
DefaultConversionService conversionService =
    new DefaultConversionService();

conversionService.addConverter(
    new StringToCurrencyCodeConverter()
);
```

`DefaultConversionService` đăng ký sẵn các converter phổ biến cho String, số, enum, collection và nhiều kiểu cơ bản. Ta bổ sung converter riêng bằng `addConverter`. Nó cũng là một `ConverterRegistry` để đăng ký trực tiếp.

Nếu ứng dụng chỉ tạo converter cho một ngữ cảnh cụ thể, có thể tạo instance riêng. Tránh thay đổi registry sau khi nó đã được nhiều thread sử dụng; đăng ký converter lúc cấu hình ứng dụng rồi giữ cấu hình ổn định.

### 4.2. Đăng ký trong ApplicationContext bằng tên bean quy ước

Với Spring ApplicationContext, một `ConversionService` được đăng ký dưới tên bean `conversionService` sẽ được framework nhận diện như service chuyển đổi mặc định của context.

Ví dụ cấu hình Java:

```java
@Configuration
public class ConversionConfiguration {

    @Bean
    public ConversionService conversionService() {
        DefaultConversionService service =
            new DefaultConversionService();

        service.addConverter(
            new StringToCurrencyCodeConverter()
        );
        return service;
    }
}
```

Đây là fragment cấu hình; cần import `@Configuration`, `@Bean`, `ConversionService` và `DefaultConversionService`. Vì phương thức `@Bean` có tên `conversionService`, tên bean mặc định khớp convention của Spring. Khi container sử dụng conversion service này, custom converter tham gia việc chuyển đổi property/constructor values.

Có thể cấu hình bằng XML:

```xml
<bean id="conversionService"
      class="org.springframework.context.support.ConversionServiceFactoryBean">
    <property name="converters">
        <set>
            <bean class="example.StringToCurrencyCodeConverter"/>
        </set>
    </property>
</bean>
```

Đây là ví dụ cho class top-level `example.StringToCurrencyCodeConverter` có constructor phù hợp; ứng dụng phải nạp file XML trong đúng context. `ConversionServiceFactoryBean` tạo service từ các converter được khai báo.

### 4.3. Đăng ký thủ công trên BeanFactory

Ở tầng thấp hơn, API `ConfigurableBeanFactory` cho phép gắn service trực tiếp:

```java
ConfigurableListableBeanFactory beanFactory =
    context.getBeanFactory();

beanFactory.setConversionService(conversionService);
```

Đây là fragment phụ thuộc context và thời điểm lifecycle. Cần đặt conversion service **trước khi bean cần conversion được tạo**. Trong ứng dụng thông thường, dùng bean tên `conversionService` là cách cấu hình chuẩn; gọi thủ công hữu ích trong ví dụ tích hợp hoặc khi thao tác với bean factory ở mức thấp.

Đừng nhầm `beanFactory.setConversionService` với `binder.setConversionService`. Cùng một service có thể được truyền vào cả hai, nhưng chúng là hai điểm nhận cấu hình độc lập.

## 5. Tích hợp ConversionService với BeanFactory

### 5.1. Bean definition chứa property value dạng String

Giả sử:

```java
public static class PaymentSettings {
    private CurrencyCode currency;

    public CurrencyCode getCurrency() {
        return currency;
    }

    public void setCurrency(CurrencyCode currency) {
        this.currency = currency;
    }
}
```

Khi bean definition chứa `currency = " usd "`, setter yêu cầu `CurrencyCode`. BeanFactory cần chuyển giá trị trước khi gọi setter. Với service đã đăng ký:

```text
RootBeanDefinition:
  beanClass = PaymentSettings
  property "currency" = " usd "
          |
          v
BeanFactory resolves property value
          |
          v
ConversionService.convert(String, CurrencyCode)
          |
          v
CurrencyCode("USD")
          |
          v
PaymentSettings.setCurrency(...)
```

Conversion xảy ra khi container populate bean. Nếu converter ném exception, bean creation có thể thất bại; Spring bọc lỗi theo exception của quá trình tạo bean, và cause chain chứa nguyên nhân conversion.

### 5.2. Với constructor argument

BeanFactory cũng thực hiện type conversion cho constructor arguments trong bean definition nếu giá trị cấu hình cần chuyển sang tham số constructor. Ví dụ:

```java
public class PaymentSettings {
    private final CurrencyCode currency;

    public PaymentSettings(CurrencyCode currency) {
        this.currency = currency;
    }

    public CurrencyCode getCurrency() {
        return currency;
    }
}
```

Nếu bean definition đưa một giá trị String vào constructor argument có kiểu `CurrencyCode`, conversion service của bean factory có thể tham gia resolve argument. Kết quả còn tùy metadata constructor và bean definition có đủ thông tin để Spring xác định kiểu/argument đúng.

Không áp dụng conversion nếu chính method cấu hình Java đã tạo object đúng kiểu:

```java
return new PaymentSettings(new CurrencyCode("USD"));
```

Đoạn trên tự tạo `CurrencyCode`; không có String nào cần convert.

### 5.3. Phân biệt với PropertyEditor

BeanFactory truyền thống có thể dùng JavaBeans PropertyEditor để convert property. Khi `ConversionService` phù hợp đã cấu hình, đây là cơ chế chuyển đổi thống nhất được ưu tiên. Nếu ứng dụng vẫn có custom editor, cần kiểm thử hành vi ưu tiên ở property/type cụ thể, tránh hai hệ thống cùng đăng ký quy tắc khác nhau cho một kiểu.

## 6. Tích hợp ConversionService với DataBinder

### 6.1. Gắn service cho binder

`DataBinder` có API:

```java
PaymentForm form = new PaymentForm();
DataBinder binder = new DataBinder(form, "paymentForm");

binder.setConversionService(conversionService);
```

Sau khi được cấu hình, binder sử dụng service trong lúc bind `PropertyValues` vào target. Với Spring MVC, `WebDataBinder` kế thừa API này nên có thể gắn service trong `@InitBinder` hoặc dùng conversion service tích hợp của MVC.

Ví dụ dữ liệu:

```text
currency=eur
```

Kết quả mong muốn là `form.getCurrency()` trả `CurrencyCode("EUR")` nếu form có property ghi được và binder đã nhận converter.

### 6.2. Bind dữ liệu và kiểm tra BindingResult

```java
MutablePropertyValues values = new MutablePropertyValues();
values.add("currency", "eur");

binder.bind(values);

BindingResult result = binder.getBindingResult();
if (result.hasErrors()) {
    // Trả lỗi về giao diện hoặc tầng gọi
}
```

Đây là fragment, cần imports `MutablePropertyValues` và `BindingResult`. `DataBinder.bind` xử lý property binding; nó không gọi constructor binding. Nếu muốn kiểm tra constructor binding, luồng API là `binder.construct(valueResolver)`. Đây là hai thao tác khác nhau dù cả hai đều có conversion service.

Nếu converter từ chối `"invalid"`, DataBinder có thể lưu lỗi field trong `BindingResult` thay vì để caller luôn phải tự bắt exception trực tiếp. Kiểm tra `result.getFieldErrors("currency")` và `result.hasErrors()` trước khi dùng target. Các lỗi cấu hình hoặc lỗi tạo target vẫn có thể phát sinh exception tùy tình huống.

### 6.3. WebDataBinder trong Spring MVC

Ví dụ tích hợp:

```java
@Controller
public class PaymentController {

    @InitBinder("paymentForm")
    void configure(WebDataBinder binder) {
        binder.setConversionService(conversionService);
    }

    @PostMapping("/payments")
    String submit(
            @ModelAttribute("paymentForm") PaymentForm form,
            BindingResult errors) {
        if (errors.hasErrors()) {
            return "payment-form";
        }
        paymentService.save(form);
        return "redirect:/payments";
    }
}
```

Đây là fragment cần controller có dependency `conversionService`, `paymentService`, form model và imports thích hợp. `@InitBinder` chỉ áp dụng cho binder của model attribute phù hợp. Trong cấu hình MVC chuẩn, framework thường đã có formatting/conversion service; không nên tạo thêm một service riêng trong từng controller nếu có thể cấu hình dùng chung ở tầng MVC.

Nếu sử dụng `WebMvcConfigurer.addFormatters(FormatterRegistry registry)`, có thể đăng ký converter/formatter cho MVC. Cơ chế này đưa conversion vào môi trường web; nó không thay thế cấu hình riêng cho một `BeanFactory` thuần được tạo ngoài context MVC.

## 7. Cùng một converter trong hai luồng: ví dụ Java 17 chạy được

Ví dụ dưới đây chứng minh một `StringToCurrencyCodeConverter` được đăng ký một lần trên `DefaultConversionService` và **cùng instance service** được gắn vào:

1. BeanFactory qua `ConfigurableBeanFactory.setConversionService` để populate một bean từ bean definition.
2. DataBinder qua `DataBinder.setConversionService` để bind một form object từ `MutablePropertyValues`.

### 7.1. Cấu trúc project

```text
conversion-integration-demo/
├── pom.xml
└── src/main/java/example/ConversionIntegrationDemo.java
```

`pom.xml` (Java 17 và Spring Framework 6.2.14):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>conversion-integration-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.14</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.1</version>
        <configuration>
          <mainClass>example.ConversionIntegrationDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

`src/main/java/example/ConversionIntegrationDemo.java`:

```java
package example;

import java.util.Locale;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.beans.factory.support.RootBeanDefinition;
import org.springframework.context.support.GenericApplicationContext;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.validation.DataBinder;
import org.springframework.validation.BindingResult;

public class ConversionIntegrationDemo {

    public record CurrencyCode(String value) {}

    public static final class StringToCurrencyCodeConverter
            implements Converter<String, CurrencyCode> {

        @Override
        public CurrencyCode convert(String source) {
            if (source == null || source.isBlank()) {
                throw new IllegalArgumentException("Currency code is blank");
            }
            String code =
                source.strip().toUpperCase(Locale.ROOT);
            if (!code.matches("[A-Z]{3}")) {
                throw new IllegalArgumentException(
                    "Currency code must have three letters"
                );
            }
            return new CurrencyCode(code);
        }
    }

    public static class PaymentSettings {
        private CurrencyCode currency;

        public CurrencyCode getCurrency() {
            return currency;
        }

        public void setCurrency(CurrencyCode currency) {
            this.currency = currency;
        }
    }

    public static class PaymentForm {
        private CurrencyCode currency;

        public CurrencyCode getCurrency() {
            return currency;
        }

        public void setCurrency(CurrencyCode currency) {
            this.currency = currency;
        }
    }

    public static void main(String[] args) {
        DefaultConversionService conversionService =
            new DefaultConversionService();
        conversionService.addConverter(
            new StringToCurrencyCodeConverter()
        );

        try (GenericApplicationContext context =
                 new GenericApplicationContext()) {

            ConfigurableListableBeanFactory beanFactory =
                context.getDefaultListableBeanFactory();

            // Tích hợp số 1: bean definition -> BeanFactory.
            beanFactory.setConversionService(conversionService);

            RootBeanDefinition definition =
                new RootBeanDefinition(PaymentSettings.class);
            definition.getPropertyValues().add("currency", " usd ");
            context.registerBeanDefinition("paymentSettings", definition);

            context.refresh();

            PaymentSettings settings =
                context.getBean("paymentSettings", PaymentSettings.class);

            // Tích hợp số 2: request-like values -> DataBinder.
            PaymentForm form = new PaymentForm();
            DataBinder binder = new DataBinder(form, "paymentForm");
            binder.setConversionService(conversionService);

            MutablePropertyValues values = new MutablePropertyValues();
            values.add("currency", " eur ");
            binder.bind(values);

            BindingResult result = binder.getBindingResult();

            if (result.hasErrors()) {
                throw new IllegalStateException(
                    "Binding failed: " + result.getAllErrors()
                );
            }

            System.out.println(
                "bean=" + settings.getCurrency().value()
            );
            System.out.println(
                "binder=" + form.getCurrency().value()
            );
            System.out.println("errors=" + result.hasErrors());
        }
    }
}
```

Chạy ở thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

`stdout` dự kiến khi Maven không in log phụ:

```text
bean=USD
binder=EUR
errors=false
```

Phân tích:

- Dòng `bean=USD` chứng minh bean factory đã dùng service để chuyển `" usd "` từ bean definition thành `CurrencyCode` trước khi setter được gọi.
- Dòng `binder=EUR` chứng minh DataBinder dùng chính conversion service đó để chuyển giá trị trong `MutablePropertyValues`.
- Dòng `errors=false` cho biết binder không ghi nhận lỗi conversion trong kịch bản hợp lệ.
- Không có đoạn nào tự tạo `new CurrencyCode("USD")` để gán vào bean; conversion diễn ra qua registered converter.
- Ví dụ dùng `GenericApplicationContext` và đăng ký bean definition trước `refresh()`. BeanFactory được cấu hình service trước lúc bean `PaymentSettings` được tạo.

Để thử lỗi binder, thay `" eur "` bằng `"not-valid"`. Converter ném `IllegalArgumentException`; binder thường ghi lỗi type mismatch vào `BindingResult`. Đoạn demo cố ý ném `IllegalStateException` sau khi thấy lỗi để thể hiện ứng dụng không tiếp tục dùng form lỗi. Đối với bean definition, converter failure xảy ra trong bean creation và có thể làm `context.refresh()` thất bại.

## 8. ConversionService với collection, Map và TypeDescriptor

### 8.1. Vì sao `Class<?>` đôi khi không đủ?

API cơ bản:

```java
conversionService.canConvert(String.class, Integer.class);
Integer age = conversionService.convert("21", Integer.class);
```

Dễ dùng khi source và target là một kiểu cụ thể. Nhưng với `List<Integer>` và `List<String>`, cả hai cùng có runtime class `List.class`. Chỉ truyền `List.class` không mô tả element generic.

`TypeDescriptor` bổ sung metadata như element type, map key/value type và annotation trên field/property. Từ đó Spring có thể chuyển đổi từng phần tử theo target type chính xác.

### 8.2. Chuyển đổi collection có generic

Ví dụ:

```java
List<Integer> input = List.of(1, 2, 3);

List<String> output = (List<String>) conversionService.convert(
    input,
    TypeDescriptor.collection(
        List.class,
        TypeDescriptor.valueOf(Integer.class)
    ),
    TypeDescriptor.collection(
        List.class,
        TypeDescriptor.valueOf(String.class)
    )
);
```

Đây là fragment minh họa; cần import `TypeDescriptor`, `List` và suppression/cast phù hợp cho generic do API trả về dạng Object ở overload metadata. Với converter mặc định được đăng ký, output là danh sách `"1"`, `"2"`, `"3"`. Việc chuyển từng phần tử dùng converter `Integer → String` thích hợp.

### 8.3. Array và Map

`DefaultConversionService` cung cấp nhiều converter collection/array cơ bản và tái sử dụng converter theo kiểu phần tử khi có metadata phù hợp. Với Map, cần mô tả cả kiểu key và value; nếu chuyển đổi Map có generic khác nhau, hãy dùng `TypeDescriptor` của source/target thay vì dựa vào `Map.class` đơn thuần.

Ví dụ mô tả type descriptor của một Map:

```java
TypeDescriptor source = TypeDescriptor.map(
    Map.class,
    TypeDescriptor.valueOf(String.class),
    TypeDescriptor.valueOf(Integer.class)
);
```

Đây là fragment mô tả `Map<String, Integer>`; nó chưa tự chạy conversion nếu không truyền source object và target descriptor tương ứng vào `convert(...)`.

### 8.4. Khi nào cần GenericConverter?

Dùng `GenericConverter` khi conversion phụ thuộc cả source/target type metadata, nested generic, annotation hoặc context của property. Interface nhận một tập `ConvertiblePair` và method `convert(Object, TypeDescriptor, TypeDescriptor)`. Đây là lựa chọn linh hoạt nhưng phức tạp hơn `Converter<S,T>`. Với một kiểu đơn giản như String → CurrencyCode, `Converter` là đủ.

Không tự viết converter collection chỉ để chuyển `List<S>` sang `List<T>` nếu converter scalar cho element và default collection converters đã giải quyết được trường hợp. Hãy tận dụng conversion infrastructure trước khi tạo converter tổng hợp riêng.

## 9. Những cách cấu hình phổ biến

| Cách cấu hình | BeanFactory | DataBinder | Khi dùng |
| --- | --- | --- | --- |
| Bean `conversionService` trong ApplicationContext | Context nhận làm service chuyển đổi | Có thể dùng nếu binder được MVC/context cấu hình tương ứng | Ứng dụng Spring quản lý bằng context |
| `ConfigurableBeanFactory.setConversionService` | Gắn trực tiếp vào factory cụ thể | Không tự cấu hình binder khác | Factory tùy biến / demo thấp tầng |
| `DataBinder.setConversionService` | Không đổi factory | Gắn cho binder cụ thể | Binder tự tạo ngoài MVC |
| `@InitBinder` | Không đổi factory | Gắn hoặc điều chỉnh WebDataBinder | MVC controller, theo attribute |
| `WebMvcConfigurer.addFormatters` | Không mặc nhiên cấu hình bean factory thuần | Đăng ký converter/formatter cho MVC | Conversion dùng chung ở tầng Spring MVC |
| `PropertyEditorRegistrar` | Có thể tích hợp qua bean factory | Có thể tái sử dụng trên binder | Tương thích code legacy |

### 9.1. Java configuration với converter dùng chung

Một ứng dụng Spring có thể cấu hình:

```java
@Configuration
public class AppConversionConfiguration {

    @Bean
    ConversionService conversionService() {
        DefaultConversionService service =
            new DefaultConversionService();
        service.addConverter(
            new StringToCurrencyCodeConverter()
        );
        return service;
    }
}
```

Khi Spring context phát hiện bean tên `conversionService`, service được dùng trong conversion của framework. Với cấu hình MVC riêng, `FormattingConversionService`/`FormatterRegistry` có thể là nơi đăng ký formatter/converter bổ sung, tùy loại ứng dụng và cấu hình MVC.

### 9.2. Spring MVC explicit formatter registration

```java
@Configuration
public class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
            new StringToCurrencyCodeConverter()
        );
    }
}
```

Đây là fragment MVC: cần imports `WebMvcConfigurer`, `FormatterRegistry`, `Configuration`. Nếu đã có converter trong conversion service MVC dùng chung, không cần đăng ký trùng. Cách này nhắm vào conversion/formatting web; bean factory thuần vẫn cần service ở context tương ứng.

## 10. Phối hợp PropertyEditor và ConversionService

Spring cho phép cả hai hệ thống tồn tại. Với loại legacy chưa thể chuyển ngay sang converter, có thể giữ custom `PropertyEditor` tại một số registry. Tuy nhiên, một kiểu có nhiều quy tắc chuyển đổi khác nhau dễ khiến hành vi khó đoán.

Thứ tự thực tế còn phụ thuộc property accessor, type converter và custom editor được đăng ký theo loại/path. Vì vậy:

- Ưu tiên converter stateless cho phép chuyển đổi kiểu tổng quát.
- Chỉ dùng property-specific editor khi thực sự cần trạng thái hoặc ngữ nghĩa JavaBeans đặc thù.
- Không đăng ký hai quy tắc cùng mục tiêu nhưng khác chuẩn hóa/validation mà không có test phân xử.
- Không nghĩ một `ConversionService` loại bỏ mọi `PropertyEditor` trong ứng dụng; hai API có thể cùng tồn tại.
- Với editor có state, tạo instance phù hợp cho mỗi registry/binder và tránh dùng chung singleton mutable.

## 11. Lỗi thường gặp và chẩn đoán

### 11.1. Chỉ đăng ký converter vào nhầm service

Bạn gọi `conversionService.addConverter(...)` trên instance A, nhưng binder được cấu hình instance B. Kết quả là binder báo không thể convert. So sánh đúng reference được truyền vào `setConversionService`, không chỉ kiểm tra class converter có tồn tại trong source code.

### 11.2. Gắn service quá muộn

Nếu bean đã được tạo trước khi gọi `beanFactory.setConversionService(...)`, conversion trong lần tạo đó đã xảy ra. Cấu hình service trước `refresh()` hoặc trước khi bean đích được instantiate; trong context thông thường dùng bean có tên chuẩn `conversionService`.

### 11.3. Converter không khớp kiểu

`Converter<String, CurrencyCode>` không xử lý tự động `Object → CurrencyCode` hay `String → một kiểu khác`. Kiểm tra source/target descriptors và đăng ký converter đúng pair. Nếu chuyển đổi theo hierarchy, xem `ConverterFactory` hoặc `GenericConverter`.

### 11.4. Sai kiểu container do generic bị mất

`List.class` không nói element là `Integer` hay `String`. Với conversion generic, dùng `TypeDescriptor`; trong bean property binding, metadata property thường cho Spring biết generic type. Khi gọi API convert thủ công, caller cần cung cấp descriptors tương ứng.

### 11.5. Converter ném exception

Converter nên báo input không hợp lệ bằng unchecked exception thích hợp, thông thường `IllegalArgumentException`. Trong DataBinder, lỗi có thể trở thành FieldError; trong bean creation, conversion failure có thể làm bean không được tạo. Không swallow exception rồi trả object mặc định sai nghĩa.

### 11.6. Nghĩ converter tự validate business object

Converter chỉ chịu trách nhiệm biến đổi biểu diễn/kiểu dữ liệu. `CurrencyCode("USD")` có hình dạng hợp lệ theo ví dụ, nhưng việc tài khoản có quyền giao dịch USD, tỷ giá áp dụng hay payment method hỗ trợ USD là logic nghiệp vụ riêng. Validate sau conversion hoặc trong service.

### 11.7. Nhầm với JSON deserialization

`@RequestBody` thường dùng `HttpMessageConverter` và JSON mapper. ConversionService không tự động thay toàn bộ Jackson deserializer. Với JSON custom scalar, cấu hình JSON mapper phù hợp hoặc thiết kế deserializer; converter có thể vẫn được dùng trong các bước binding khác.

### 11.8. Thay đổi registry khi nhiều thread đã sử dụng

`ConversionService` được thiết kế stateless và dùng chung sau khi cấu hình. Đăng ký converter mới trong lúc request chạy có thể gây hành vi cấu hình khó kiểm soát. Hoàn tất registry ở startup rồi coi như immutable trong vận hành.

## 12. Kiểm thử tích hợp hai boundary

Nên có ít nhất ba nhóm test:

1. **BeanFactory test:** đăng ký converter/service, tạo bean từ bean definition chứa String, xác minh setter nhận đúng kiểu/value.
2. **DataBinder test:** tạo target, gắn service, bind property values, xác minh target và `BindingResult`.
3. **Failure test:** gửi chuỗi sai, xác minh binder ghi lỗi phù hợp và bean creation không thành công theo kỳ vọng.

Ví dụ test binder ngắn:

```java
@Test
void dataBinderUsesCurrencyConverter() {
    DefaultConversionService service =
        new DefaultConversionService();
    service.addConverter(new StringToCurrencyCodeConverter());

    PaymentForm form = new PaymentForm();
    DataBinder binder = new DataBinder(form);
    binder.setConversionService(service);

    MutablePropertyValues values = new MutablePropertyValues();
    values.add("currency", " usd ");
    binder.bind(values);

    assertFalse(binder.getBindingResult().hasErrors());
    assertEquals("USD", form.getCurrency().value());
}
```

Đây là fragment test dùng JUnit 5 và các class demo. Cần imports/fixture tương ứng; test chứng minh DataBinder conversion, không chứng minh BeanFactory integration. Hai boundary phải có test riêng vì cấu hình một bên không đảm bảo bên còn lại tự động hoạt động.

## 13. Checklist chọn và cấu hình đúng

- Đang chuyển đổi ở **BeanFactory** hay ở **DataBinder**? Nếu cả hai, đã gắn service vào cả hai nơi?
- Bean có tên `conversionService` trong ApplicationContext đúng context chưa?
- Nếu thao tác thấp tầng, `ConfigurableBeanFactory` và `DataBinder` đã được cấu hình trước khi dùng chưa?
- Converter có source/target type rõ, stateless, thread-safe không?
- Input null/blank/sai format được xử lý nhất quán và có test?
- Với List/Map/array có generic, có cần `TypeDescriptor` để cung cấp metadata?
- Có đang dùng `PropertyEditor` cũ cùng converter cho một kiểu gây xung đột không?
- Đã phân biệt type conversion với validation và authorization chưa?
- Nếu là JSON `@RequestBody`, đã kiểm tra cơ chế mapper/deserializer thực tế?
- Đã viết test riêng cho bean definition, binder và trường hợp lỗi?

## 14. Bài tập tự kiểm tra

### Bài 1 — Xác định đúng điểm đăng ký

Một converter `String → CurrencyCode` đã được thêm vào `DefaultConversionService A`. Một bean factory được cấu hình với `DefaultConversionService B`. Một DataBinder được cấu hình với A. Luồng nào dùng converter?

**Đáp án:** DataBinder dùng A nên thấy converter; bean factory dùng B nên không tự thấy converter của A. Cần đăng ký converter trên B hoặc gắn cùng service A vào bean factory.

### Bài 2 — Dự đoán kết quả

Converter loại khoảng trắng và chuyển uppercase. Bean definition chứa `currency=" eur "`. Setter nhận `CurrencyCode`. Giá trị là gì?

**Đáp án:** `CurrencyCode("EUR")` nếu bean factory đã gắn đúng ConversionService và conversion không lỗi.

### Bài 3 — Vì sao TypeDescriptor cần thiết?

Một method gọi `convert(inputList, List.class)` với `List<Integer>` và muốn `List<String>`. Tại sao chỉ Class không đủ?

**Đáp án:** runtime class của cả hai là `List.class`. Cần `TypeDescriptor.collection(...)` mô tả kiểu element nguồn/đích để Spring chuyển từng phần tử.

### Bài 4 — Conversion có thay validation không?

Chuỗi `"USD"` chuyển thành `CurrencyCode("USD")` thành công. Có thể khẳng định giao dịch hiện tại được phép dùng USD không?

**Đáp án:** Không. Converter chỉ chuẩn hóa/chuyển kiểu; quyền giao dịch và quy tắc nghiệp vụ phải kiểm tra tại service/domain.

## 15. Tài liệu tham khảo chính thức

- Spring Framework Reference — [Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): `ConversionService`, `Converter`, registry, default service và `TypeDescriptor`.
- Spring Framework Reference — [Core Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): `DataBinder`, property binding và conversion.
- Spring Framework Javadoc — [ConfigurableBeanFactory](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/config/ConfigurableBeanFactory.html): `setConversionService` và cách bean factory dùng type conversion.
- Spring Framework Javadoc — [DataBinder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/DataBinder.html): `setConversionService` và cơ chế bind.
- Spring Framework Javadoc — [DefaultConversionService](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/support/DefaultConversionService.html): converter mặc định, registry và hỗ trợ conversion.
- Spring Framework Reference — [Conversion and Formatting in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html): cấu hình converter/formatter ở tầng MVC.
