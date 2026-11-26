# Rà lại converter cũ và cơ chế định dạng của Spring

## Mục tiêu bài học

Trong ứng dụng Spring Web Flow lâu năm, logic chuyển đổi dữ liệu có thể nằm rải rác ở nhiều nơi: converter của Spring Binding, converter có tên trong XML, `PropertyEditor`, `@InitBinder`, formatter của Spring MVC và cấu hình `flow-builder-services`. Khi nâng cấp, chỉ thay một class converter hoặc thêm một formatter vào MVC chưa chắc đã thay đổi được cách `view-state` bind dữ liệu.

Spring Web Flow đã sử dụng hệ thống **type conversion và field formatting của Spring** cho hầu hết nhu cầu chuyển đổi từ phiên bản 2.1. Tuy vậy, cơ chế cũ vẫn tồn tại để tương thích ngược. Bài học này giúp bạn kiểm kê và di chuyển từng loại converter theo đúng đường chạy, giữ ứng dụng hoạt động trong quá trình nâng cấp.

Sau bài học, bạn có thể:

1. Phân biệt `org.springframework.binding.convert.converters.Converter` với `org.springframework.core.convert.converter.Converter`.
2. Nhận diện converter cũ được adapter sang Spring `GenericConverter` và **named converter** còn chạy theo cơ chế legacy.
3. Hiểu vì sao thuộc tính `converter="..."` trên `<binding>` là dấu hiệu cần rà soát.
4. Phân biệt `Converter`, `ConverterFactory`, `GenericConverter`, `Formatter` và `PropertyEditor`.
5. Nối `FormattingConversionService` dùng trong Spring MVC với `DefaultConversionService` của Spring Binding trong Web Flow.
6. Di chuyển logic định dạng chuỗi theo locale sang `Formatter`, dùng annotation hoặc kiểu dữ liệu chuyên biệt.
7. Giữ converter cũ trong giai đoạn chuyển tiếp mà không vô tình đăng ký nhầm vào registry.
8. Lập kế hoạch kiểm thử và loại bỏ named converter sau khi đã xác nhận hành vi tương đương.

## 1. Bối cảnh: từ cơ chế chuyển đổi cũ sang Spring Type Conversion

Trong những phiên bản Web Flow cũ, data binding có thể dựa vào `java.beans.PropertyEditor` và cơ chế converter riêng của Spring Binding. Khi Spring giới thiệu hệ thống `core.convert` và field formatting, Web Flow chuyển dần sang dùng chung cơ chế với Spring MVC.

Theo tài liệu Spring Web Flow, từ phiên bản **2.1**, Web Flow sử dụng hệ thống type conversion và formatting của Spring cho gần như mọi nhu cầu chuyển đổi. Điều này cho phép Spring MVC và Web Flow dùng chung converter/formatter. Tuy nhiên, một số API cũ được giữ lại để ứng dụng hiện hữu có thể nâng cấp từng bước.

### Những cơ chế có thể cùng tồn tại trong một ứng dụng cũ

| Cơ chế | API tiêu biểu | Vị trí thường gặp | Tình trạng khi nâng cấp |
| --- | --- | --- | --- |
| Spring Binding converter | `org.springframework.binding.convert.converters.Converter` | Subclass `DefaultConversionService` | Converter không đặt tên vẫn có thể được adapter sang Spring type conversion |
| Named Spring Binding converter | `addConverter("id", converter)` | `<binding converter="id"/>` | Tương thích ngược, deprecated; không thuộc Spring type conversion |
| Spring core converter | `org.springframework.core.convert.converter.Converter` | `ConversionService`/`ConverterRegistry` | Cơ chế khuyến nghị cho chuyển đổi object-to-object |
| Spring formatter | `org.springframework.format.Formatter` | `FormattingConversionService` | Cơ chế khuyến nghị cho parse/print chuỗi có locale |
| `PropertyEditor` | `java.beans.PropertyEditor` | `PropertyEditorRegistrar`, `@InitBinder`, `FormAction` | API cũ; cần kiểm tra phạm vi đăng ký và tính thread-safe |
| Annotation định dạng | `@DateTimeFormat`, `@NumberFormat` | Field/property của model | Dùng với Spring formatting service đã cấu hình |

**Điểm quan trọng:** không phải mọi converter thuộc package Spring Binding đều bị loại bỏ. Tài liệu phân biệt rõ converter được đăng ký không tên với converter có ID. Named converter là ngoại lệ không được adapter vào Spring type conversion.

## 2. Phân biệt hai interface cùng tên `Converter`

Một nguyên nhân phổ biến gây nhầm lẫn là cả Spring Binding và Spring Framework đều có interface tên `Converter`, nhưng package, chữ ký và cách đăng ký khác nhau.

### 2.1. Converter cũ của Spring Binding

Giả sử ứng dụng có value object đơn giản:

```java
public record CustomerCode(String value) {
    public CustomerCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Mã khách hàng là bắt buộc");
        }
    }
}
```

```java
import org.springframework.binding.convert.converters.Converter;

public class LegacyStringToCustomerCodeConverter implements Converter {

    @Override
    public Class<?> getSourceClass() {
        return String.class;
    }

    @Override
    public Class<?> getTargetClass() {
        return CustomerCode.class;
    }

    @Override
    public Object convertSourceToTargetClass(
            Object source, Class<?> targetClass) {
        if (source == null) {
            return null;
        }
        String value = source.toString().trim();
        return value.isEmpty() ? null : new CustomerCode(value);
    }
}
```

Đây là API Spring Binding:

- `getSourceClass()` khai báo kiểu đầu vào.
- `getTargetClass()` khai báo kiểu đích.
- `convertSourceToTargetClass(...)` thực hiện chuyển đổi.
- Converter có thể khai báo kiểu nguồn là interface hoặc lớp trừu tượng để chấp nhận các kiểu con phù hợp.

Một converter chỉ chuyển một chiều có thể implement `Converter`. Nếu cần chuyển đổi ngược, Spring Binding có interface `TwoWayConverter`. Không nên giả định mọi converter cũ đều có khả năng in ngược ra chuỗi.

### 2.2. Converter của Spring Framework

```java
import org.springframework.core.convert.converter.Converter;

public class StringToCustomerCodeConverter
        implements Converter<String, CustomerCode> {

    @Override
    public CustomerCode convert(String source) {
        if (source == null || source.isBlank()) {
            return null;
        }
        return new CustomerCode(source.trim());
    }
}
```

Đây là API Spring Core:

- Kiểu nguồn và kiểu đích được khai báo bằng generic.
- Method là `convert(S source)`.
- Converter được đăng ký vào Spring `ConverterRegistry`/`ConversionService`.
- Đây là chuyển đổi object-to-object tổng quát; không tự cung cấp cơ chế format theo locale.

### So sánh nhanh

| Tiêu chí | Spring Binding `Converter` | Spring Core `Converter<S,T>` |
| --- | --- | --- |
| Package | `org.springframework.binding.convert.converters` | `org.springframework.core.convert.converter` |
| Chữ ký | `convertSourceToTargetClass(Object, Class<?>)` | `convert(S)` |
| Khai báo kiểu | `getSourceClass()` và `getTargetClass()` | Generic `S`, `T` |
| Đăng ký | Spring Binding `DefaultConversionService` | Spring `ConverterRegistry` |
| Tương thích Web Flow | Có adapter cho converter đăng ký không tên | Là cơ chế Spring type conversion trực tiếp |
| Khuyến nghị cho code mới | Chỉ giữ tạm khi cần tương thích | Nên dùng |

**Không đổi import máy móc.** Một class có thể vẫn compile sau khi đổi import nhưng method không còn đúng chữ ký, hoặc converter được đăng ký vào một service khác với service mà `view-state` đang dùng.

## 3. Hai kiểu đăng ký converter cũ có hành vi khác nhau

Đây là phần quan trọng nhất khi kiểm kê ứng dụng.

### 3.1. Đăng ký converter cũ không tên

Tài liệu Spring Web Flow mô tả rằng converter kiểu `org.springframework.binding.convert.converters.Converter` đăng ký qua `addConverter(converter)` có thể tiếp tục được sử dụng. Web Flow adapter converter đó thành một Spring `GenericConverter` và đăng ký vào Spring `org.springframework.core.convert.ConversionService`.

```java
import org.springframework.binding.convert.service.DefaultConversionService;
import org.springframework.binding.convert.converters.Converter;

public class LegacyAwareConversionService extends DefaultConversionService {

    public LegacyAwareConversionService() {
        addConverter(new LegacyStringToCustomerCodeConverter());
    }
}
```

Ở ví dụ này, `LegacyStringToCustomerCodeConverter` implement interface Spring Binding cũ. Lệnh `addConverter(converter)` không truyền ID; converter được adapter để tham gia cơ chế chuyển đổi theo cặp kiểu nguồn/đích.

Đây là **cầu nối tương thích**, không phải lý do để tiếp tục viết converter mới bằng API cũ. Khi sửa logic, hãy ưu tiên chuyển sang Spring Core `Converter` hoặc `Formatter`.

### 3.2. Đăng ký converter có tên

Ứng dụng cũ có thể chứa:

```java
import org.springframework.binding.convert.service.DefaultConversionService;

public class ApplicationConversionService
        extends DefaultConversionService {

    public ApplicationConversionService() {
        addDefaultConverters();
        addDefaultAliases();
        addConverter("customerCode", new LegacyStringToCustomerCodeConverter());
    }
}
```

Và trong flow:

```xml
<view-state id="editCustomer" model="customer">
    <binder>
        <binding property="customerCode"
                 required="true"
                 converter="customerCode" />
    </binder>
</view-state>
```

Ở đây `converter="customerCode"` tham chiếu **named converter**. Theo tài liệu Web Flow:

- Named converter không được hỗ trợ bởi Spring type conversion.
- Converter này không được adapter vào Spring `ConversionService`.
- Cơ chế cũ vẫn hoạt động theo đường riêng để tương thích ngược.
- Cơ chế named converter đã deprecated và ứng dụng được khuyến nghị chuyển sang Spring type conversion/formatting.

Nói cách khác, một flow vẫn có thể chạy nhờ named converter trong khi Spring MVC đã dùng formatter mới. Khi đó cùng một kiểu dữ liệu có thể được parse khác nhau tùy đường request đi qua MVC hay Web Flow.

### 3.3. Đừng nhầm `addConverter` với `addConverter(id, ...)`

| Lời gọi | Ý nghĩa | Đường chuyển đổi |
| --- | --- | --- |
| `addConverter(legacyConverter)` | Đăng ký converter cũ không tên | Adapter vào Spring type conversion |
| `addConverter("customerCode", legacyConverter)` | Đăng ký converter theo ID | Đường named converter cũ |
| `registry.addConverter(springConverter)` | Đăng ký Spring Core converter | Spring type conversion |
| `registry.addFormatter(formatter)` | Đăng ký Spring formatter | Spring type conversion + formatting |

Chỉ nhìn thấy `addConverter` trong source là chưa đủ. Hãy xem overload nào được gọi và kiểm tra có `converter="..."` tương ứng trong XML hay không.

## 4. `DefaultConversionService` của Spring Binding không phải Spring `ConversionService`

Hai class có tên gần giống nhưng thuộc package khác nhau:

```java
// Spring Binding / Web Flow
org.springframework.binding.convert.service.DefaultConversionService

// Spring Framework
org.springframework.core.convert.support.DefaultConversionService
```

Không import nhầm hai class này.

### Vai trò của Spring Binding `DefaultConversionService`

Spring Binding cung cấp một adapter/service cho Web Flow. Từ Web Flow 2.1, phần lớn chuyển đổi được ủy quyền sang Spring type conversion. Constructor nhận một Spring `org.springframework.core.convert.ConversionService` để làm delegate:

```java
org.springframework.binding.convert.service.DefaultConversionService(
        org.springframework.core.convert.ConversionService delegate)
```

Vì vậy, khi cấu hình Web Flow:

```xml
<bean id="webFlowConversionService"
      class="org.springframework.binding.convert.service.DefaultConversionService">
    <constructor-arg ref="applicationConversionService" />
</bean>
```

`webFlowConversionService` là service ở lớp Spring Binding; `applicationConversionService` là Spring conversion service thật chứa converter/formatter. Wrapper giúp Web Flow tích hợp với API Spring Binding nhưng ủy quyền việc chuyển đổi thông thường cho Spring Framework.

### Các converter mặc định được lấy từ đâu?

Tài liệu API cho biết từ Web Flow 2.1, `DefaultConversionService.addDefaultConverters()` không còn đăng ký các Spring Binding converter mặc định. Việc chuyển đổi mặc định dựa vào Spring type conversion. Vì vậy:

- Không cần sao chép một danh sách converter cũ vào từng flow.
- Không nên giả định `DefaultConversionService` Spring Binding có bộ converter độc lập như trong ứng dụng rất cũ.
- Khi thiếu chuyển đổi, hãy kiểm tra Spring delegate và formatter/converter đã đăng ký.
- Kiểm tra cả aliases nếu ứng dụng dùng tên kiểu trong expression hoặc mapping cũ.

## 5. Kiểm kê ứng dụng trước khi sửa

Trước khi nâng cấp, hãy lập danh sách toàn bộ điểm đăng ký và sử dụng conversion. Mục tiêu là biết converter nào còn cần, converter nào đã trùng với Spring mặc định và converter nào đang chạy qua đường deprecated.

### 5.1. Từ khóa nên tìm trong code và XML

| Từ khóa | Điều cần kiểm tra |
| --- | --- |
| `org.springframework.binding.convert.converters.Converter` | Class còn implement converter cũ không? |
| `org.springframework.binding.convert.service.DefaultConversionService` | Có subclass hoặc bean riêng không? |
| `addConverter(` | Đang gọi overload có ID hay không ID? |
| `converter="` | Có binding nào phụ thuộc named converter không? |
| `PropertyEditorSupport` | Có editor tùy chỉnh và state mutable không? |
| `PropertyEditorRegistrar` | Editor được đăng ký ở MVC, FormAction hay binder nào? |
| `registerCustomEditors` | Có logic chuyển đổi cũ cần di chuyển không? |
| `@InitBinder` | MVC controller đang cấu hình editor/formatter nào? |
| `@DateTimeFormat`, `@NumberFormat` | Annotation có được service thực tế nhận diện không? |
| `FormattingConversionServiceFactoryBean` | Có service formatter dùng chung chưa? |
| `mvc:annotation-driven` | MVC đang dùng conversion-service bean nào? |
| `flow-builder-services` | Web Flow đang dùng conversion service nào? |

Ví dụ tìm trong repository bằng ripgrep:

```bash
rg -n "binding\.convert\.converters\.Converter|addConverter\(|converter=\"|PropertyEditorSupport|PropertyEditorRegistrar|registerCustomEditors|@InitBinder|@DateTimeFormat|FormattingConversionServiceFactoryBean|flow-builder-services" .
```

Nếu repository lớn, giới hạn phạm vi source/config liên quan ứng dụng. Khi kiểm kê, không chỉ đọc nơi khai báo converter mà còn tìm **nơi sử dụng**: XML flow, form model, controller và test fixture.

### 5.2. Lập bảng inventory

| Converter/editor | Source → target | Nơi đăng ký | Nơi sử dụng | Mức ưu tiên |
| --- | --- | --- | --- | --- |
| `StringToCustomerCodeConverter` | `String` → `CustomerCode` | Binding service, không tên | `customerCode` | Giữ tạm rồi chuyển |
| `LegacyDateEditor` | `String` ↔ `Date` | `@InitBinder` | MVC form | Chuyển sang formatter |
| `money` named converter | `String` → `Money` | `addConverter("money", ...)` | `<binding converter="money"/>` | Cao, deprecated |
| `StringToStatusConverter` | `String` → `Status` | Spring core registry | MVC và Web Flow | Giữ, kiểm thử |
| `LocalDateFormatter` | `String` ↔ `LocalDate` | `FormattingConversionService` | Form ngày | Giữ, chuẩn hóa đăng ký |

Ghi thêm:

- Locale nào đang được dùng?
- Pattern có cố định hay phụ thuộc locale?
- Giá trị rỗng được parse thành `null`, chuỗi rỗng hay lỗi?
- Có phân biệt chữ hoa/chữ thường?
- Có trim khoảng trắng?
- Lỗi parse được chuyển thành binding error nào?
- View có cần in ngược object thành chuỗi không?
- Converter có truy vấn database hoặc phụ thuộc request/user không?

Đây là những khác biệt có thể làm hành vi sau nâng cấp thay đổi dù cả hai phiên bản đều compile.

## 6. Chọn abstraction mới đúng với nhu cầu

Spring có một hệ thống `ConversionService` thống nhất, nhưng các abstraction phục vụ mục tiêu khác nhau.

| Abstraction | Chuyển đổi | Locale | Ví dụ |
| --- | --- | --- | --- |
| `Converter<S,T>` | Object → object | Không có tham số locale | `String` → `CustomerCode` |
| `ConverterFactory<S,R>` | Một source type sang họ target type | Không | `String` → các enum |
| `GenericConverter` | Nhiều cặp source/target, có thể xét metadata | Không trực tiếp | Collection/map hoặc conversion phức tạp |
| `Formatter<T>` | String ↔ object | Có | `20/05/2026` ↔ `LocalDate` |
| `AnnotationFormatterFactory<A>` | Formatter dựa trên annotation | Có | Field có pattern riêng |
| `PropertyEditor` | String ↔ object theo JavaBeans API | Không có contract locale chuẩn | API legacy |

### 6.1. Dùng `Converter` cho object-to-object

```java
import org.springframework.core.convert.converter.Converter;

public class StringToCustomerCodeConverter
        implements Converter<String, CustomerCode> {

    @Override
    public CustomerCode convert(String source) {
        if (source == null || source.isBlank()) {
            return null;
        }
        return new CustomerCode(source.trim());
    }
}
```

Dùng `Converter` khi logic chỉ cần biết kiểu đầu vào và kiểu đầu ra. Ví dụ parse mã định danh, chuyển ID sang value object hoặc ánh xạ một kiểu enum.

Nếu chuyển đổi phụ thuộc user hiện tại, database, locale hoặc trạng thái request, hãy cân nhắc tách logic khỏi converter. Converter nên là thành phần xác định, dễ kiểm thử và không giữ state theo request.

### 6.2. Dùng `Formatter` cho dữ liệu nhập/hiển thị

```java
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.text.ParseException;
import java.time.LocalDate;
import java.util.Locale;

import org.springframework.format.Formatter;

public class LocalDateDmyFormatter implements Formatter<LocalDate> {

    private DateTimeFormatter formatter(Locale locale) {
        return DateTimeFormatter.ofPattern("dd/MM/uuuu", locale)
                .withResolverStyle(ResolverStyle.STRICT);
    }

    @Override
    public LocalDate parse(String text, Locale locale)
            throws ParseException {
        if (text == null || text.isBlank()) {
            return null;
        }
        try {
            return LocalDate.parse(text, formatter(locale));
        } catch (DateTimeParseException ex) {
            ParseException parseException =
                    new ParseException("Ngày không hợp lệ", 0);
            parseException.initCause(ex);
            throw parseException;
        }
    }

    @Override
    public String print(LocalDate value, Locale locale) {
        return value == null ? "" : formatter(locale).format(value);
    }
}
```

`Formatter` phù hợp với web vì có hai chiều:

- `parse`: chuỗi người dùng gửi thành object.
- `print`: object trong model thành chuỗi hiển thị.

`DateTimeFormatter` là immutable và thread-safe. Nếu dùng `SimpleDateFormat` bên trong formatter singleton, cần tạo instance riêng cho mỗi lần dùng hoặc bảo đảm an toàn luồng; không chia sẻ `SimpleDateFormat` mutable giữa request.

### 6.3. Dùng `@DateTimeFormat` cho field có quy ước rõ

```java
public class BookingForm {

    @DateTimeFormat(pattern = "dd/MM/uuuu")
    private LocalDate checkinDate;

    // Getter/setter
}
```

Annotation phù hợp khi format là metadata của thuộc tính. Nó giúp MVC và Web Flow dùng cùng quy tắc nếu cả hai đang sử dụng conversion service nhận biết annotation đó.

Không nên dựa vào annotation nếu service thực tế của Web Flow chưa được nối với Spring formatting service hoặc nếu ứng dụng dùng expression parser không hỗ trợ đầy đủ tính năng định dạng annotation.

### 6.4. Dùng `GenericConverter` khi cần metadata

`GenericConverter` phù hợp khi converter phải xử lý nhiều cặp kiểu hoặc cần xem `TypeDescriptor` của field, ví dụ metadata annotation. Đừng chọn nó chỉ vì thấy API tổng quát hơn; `Converter` và `Formatter` đơn giản hơn thường dễ hiểu và dễ kiểm thử hơn.

## 7. Di chuyển named converter sang Spring ConversionService

Giả sử ứng dụng cũ có:

```xml
<view-state id="editCustomer" model="customer">
    <binder>
        <binding property="customerCode"
                 required="true"
                 converter="customerCode" />
    </binder>
</view-state>
```

Và converter được đăng ký bằng:

```java
addConverter("customerCode", new StringToCustomerCodeConverter());
```

Hãy chuyển theo các bước:

1. Xác định source/target type thực tế của converter.
2. Viết Spring Core `Converter<String, CustomerCode>` hoặc `Formatter<CustomerCode>` tùy nhu cầu.
3. Đăng ký nó trong `FormattingConversionService`/`ConversionService` được Web Flow dùng.
4. Bỏ thuộc tính `converter="customerCode"` khỏi `<binding>`.
5. Giữ `required`, binder allow-list và validation khác như cũ.
6. Kiểm thử parse, print, empty value, lỗi và locale.

XML sau khi chuyển:

```xml
<view-state id="editCustomer" model="customer">
    <binder>
        <binding property="customerCode" required="true" />
    </binder>
</view-state>
```

Spring chọn converter theo source/target type thay vì ID converter trong XML. Vì vậy, nếu một kiểu đích có nhiều format khác nhau theo field, hãy dùng annotation/formatter có metadata hoặc tạo value object riêng để phân biệt ngữ nghĩa.

### Trường hợp cần format riêng theo từng field

Giả sử `invoiceDate` dùng `dd/MM/uuuu`, nhưng `birthDate` dùng format khác. Named converter cũ có thể khiến hai binding gọi hai converter ID khác nhau. Khi chuyển sang Spring formatting, cân nhắc:

- `@DateTimeFormat(pattern=...)` trên từng field.
- `AnnotationFormatterFactory` nếu cần annotation riêng.
- Hai value object riêng nếu chúng thực sự mang ý nghĩa khác nhau.
- Một `Formatter` dùng chung nếu format giống nhau.

Không tạo hai converter cùng source/target type với kỳ vọng Spring tự biết field nào cần chọn. Cần có metadata hoặc quy tắc chọn rõ ràng.

## 8. Kết nối conversion service giữa Spring MVC và Web Flow

Đây là bước cấu hình thường bị bỏ sót trong nâng cấp.

### 8.1. Vì sao cấu hình MVC thôi chưa đủ?

Spring MVC có thể tạo một `FormattingConversionService` qua `<mvc:annotation-driven/>`. Spring Web Flow cũng có `DefaultConversionService` riêng, delegate sang một `FormattingConversionService`. Mặc định, instance của Web Flow không nhất thiết là cùng instance với MVC.

Khi chưa đăng ký formatter riêng, khác biệt này có thể không lộ rõ. Khi thêm custom formatter vào MVC, một controller có thể bind đúng nhưng `view-state` vẫn báo `typeMismatch`.

### 8.2. Cấu hình XML dùng chung

```xml
<bean id="applicationConversionService"
      class="com.example.config.ApplicationConversionServiceFactoryBean" />

<mvc:annotation-driven
        conversion-service="applicationConversionService" />

<bean id="webFlowConversionService"
      class="org.springframework.binding.convert.service.DefaultConversionService">
    <constructor-arg ref="applicationConversionService" />
</bean>

<webflow:flow-builder-services
        id="flowBuilderServices"
        conversion-service="webFlowConversionService" />

<webflow:flow-registry
        id="flowRegistry"
        flow-builder-services="flowBuilderServices">
    <webflow:flow-location
            path="/WEB-INF/flows/customer/customer.xml" />
</webflow:flow-registry>
```

Vai trò:

- `applicationConversionService`: Spring formatting/conversion service chứa formatter và converter mới.
- `mvc:annotation-driven`: Spring MVC sử dụng service đó.
- `webFlowConversionService`: Spring Binding wrapper delegate sang cùng service.
- `flow-builder-services`: truyền wrapper cho quá trình build flow.
- `flow-registry`: phải tham chiếu đúng `flowBuilderServices`.

Đây là cấu hình minh họa; ứng dụng cần khai báo XML namespace/schema tương ứng và đảm bảo chỉ có một registry thực sự được dùng cho các flow đó.

### 8.3. Tạo factory bean đăng ký formatter

```java
import org.springframework.format.FormatterRegistry;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;
import org.springframework.format.support.FormattingConversionServiceFactoryBean;

public class ApplicationConversionServiceFactoryBean
        extends FormattingConversionServiceFactoryBean {

    @Override
    protected void installFormatters(FormatterRegistry registry) {
        DateTimeFormatterRegistrar registrar =
                new DateTimeFormatterRegistrar();
        registrar.setUseIsoFormat(true);
        registrar.registerFormatters(registry);

        registry.addFormatter(new LocalDateDmyFormatter());
        registry.addConverter(new StringToCustomerCodeConverter());
    }
}
```

Trong ví dụ:

- `DateTimeFormatterRegistrar` đăng ký formatter cho các kiểu `java.time`.
- `LocalDateDmyFormatter` phục vụ field có format ngày tùy chỉnh.
- `StringToCustomerCodeConverter` là Spring Core converter.

Nếu `LocalDateDmyFormatter` và formatter mặc định đều xử lý cùng kiểu `LocalDate`, hãy xác định rõ ưu tiên và cách đăng ký theo phiên bản Spring đang dùng. Thông thường, tránh đăng ký formatter xung đột cho cùng cặp kiểu rồi trông chờ thứ tự ngẫu nhiên.

### 8.4. Giữ một converter Spring Binding cũ trong giai đoạn chuyển tiếp

Nếu chưa thể chuyển ngay converter cũ, wrapper Web Flow có thể đăng ký converter cũ không tên qua adapter:

```java
import org.springframework.binding.convert.service.DefaultConversionService;

public class TransitionalWebFlowConversionService
        extends DefaultConversionService {

    public TransitionalWebFlowConversionService(
            org.springframework.core.convert.ConversionService delegate) {
        super(delegate);
        addConverter(new LegacyStringToCustomerCodeConverter());
    }
}
```

Bean XML:

```xml
<bean id="webFlowConversionService"
      class="com.example.config.TransitionalWebFlowConversionService">
    <constructor-arg ref="applicationConversionService" />
</bean>
```

`LegacyStringToCustomerCodeConverter` phải implement `org.springframework.binding.convert.converters.Converter`. Lệnh `addConverter(legacyConverter)` không có ID nên được adapter vào Spring type conversion. Đây là cách giữ tạm một converter chưa chuyển đổi mà vẫn có thể dùng cùng delegate Spring.

Không dùng:

```java
addConverter("customerCode", new LegacyStringToCustomerCodeConverter());
```

nếu mục tiêu là đưa converter vào Spring type conversion. Overload có ID tiếp tục chạy theo cơ chế named converter cũ.

### 8.5. Có thể trộn formatter mới và converter cũ không?

Có. Tài liệu Web Flow cho phép:

- Đăng ký `Formatter` Spring mới trong `applicationConversionService`.
- Đăng ký converter Spring Binding cũ không tên trong `webFlowConversionService`.

Điều này giúp nâng cấp từng phần. Tuy nhiên, hãy ghi lại từng converter còn cũ và đặt thời hạn loại bỏ; nếu không, lớp tương thích có thể trở thành kiến trúc vĩnh viễn khó bảo trì.

## 9. Di chuyển `PropertyEditor` và `@InitBinder`

Một ứng dụng cũ có thể dùng:

```java
public class CustomerCodeEditor extends PropertyEditorSupport {

    @Override
    public void setAsText(String text) {
        setValue(new CustomerCode(text.trim()));
    }

    @Override
    public String getAsText() {
        CustomerCode value = (CustomerCode) getValue();
        return value == null ? "" : value.value();
    }
}
```

Trong Spring MVC, editor có thể được đăng ký qua `@InitBinder`:

```java
@InitBinder
public void initBinder(WebDataBinder binder) {
    binder.registerCustomEditor(
            CustomerCode.class, new CustomerCodeEditor());
}
```

Editor được đăng ký cho binder/controller đó. Nó không tự động trở thành converter của Spring Web Flow.

### Vì sao nên chuyển sang `Formatter`?

`PropertyEditor` là API JavaBeans cũ:

- Chuyển đổi qua trạng thái nội bộ của editor.
- Thường mutable và không nên chia sẻ instance giữa các request.
- Không có tham số `Locale` chuẩn trong contract.
- Đăng ký có thể phụ thuộc controller/binder cụ thể.

`Formatter<T>` tách rõ `parse` và `print`, nhận `Locale`, và được đăng ký vào conversion service dùng chung.

### Cách di chuyển

| PropertyEditor cũ | Hướng thay thế |
| --- | --- |
| `setAsText(String)` | `Formatter.parse(String, Locale)` hoặc `Converter.convert(String)` |
| `getAsText()` | `Formatter.print(T, Locale)` |
| Pattern ngày giờ | `DateTimeFormatter`/`@DateTimeFormat` |
| Parse enum/value object | Spring Core `Converter` |
| Cần format theo locale | Spring `Formatter` |
| Editor cần metadata annotation | `AnnotationFormatterFactory` |

Không xóa `@InitBinder` trước khi xác nhận tất cả controller đã dùng formatter mới. Có thể giữ một editor cho endpoint đặc biệt trong giai đoạn chuyển tiếp, nhưng cần test riêng đường MVC và Web Flow.

### Trường hợp `FormAction` của Web Flow

API `FormAction` vẫn có hook đăng ký `PropertyEditor` cho data binder do action tạo. Đây là extension point legacy chuyên biệt. Nếu ứng dụng còn dùng `FormAction` hoặc custom action dựa trên `PropertyEditorRegistry`, hãy kiểm kê riêng; không giả định thay conversion service là mọi editor được dùng trong action cũ tự biến mất.

Với code mới, ưu tiên Spring conversion/formatting service chung. Nếu phải giữ `PropertyEditor`, hãy tạo instance mới cho binder và không chia sẻ editor mutable dạng singleton.

## 10. Format theo locale và annotation

### 10.1. `Converter` không phải formatter

Converter giải quyết việc chuyển object này sang object khác. Formatter giải quyết chuỗi nhập/xuất trong giao diện và có locale.

Ví dụ:

```text
String "1.234,50" + locale de-DE → BigDecimal
BigDecimal 1234.50 + locale vi-VN → chuỗi hiển thị theo format Việt
```

Nếu dùng converter `String → BigDecimal` tự viết, nó phải tự đoán dấu thập phân và phân tách hàng nghìn. Một `Formatter<BigDecimal>` nhận `Locale` sẽ thể hiện ý định rõ hơn.

### 10.2. Annotation định dạng

```java
public class InvoiceForm {

    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal amount;

    @DateTimeFormat(pattern = "dd/MM/uuuu")
    private LocalDate invoiceDate;

    // Getter/setter
}
```

Spring có `@NumberFormat` và `@DateTimeFormat`. Có thể đặt annotation trên thuộc tính model để chỉ rõ cách hiển thị/parse. Muốn annotation hoạt động trong Web Flow, cần bảo đảm:

1. Model được khai báo trong `view-state`.
2. Flow builder dùng đúng conversion service.
3. Formatter tương ứng được đăng ký.
4. Expression parser và cơ chế view binding của ứng dụng hỗ trợ tính năng đang dùng.

### 10.3. Kiểm tra expression parser khi annotation không được áp dụng

Spring EL tích hợp với Spring type conversion, hỗ trợ tự phát hiện generic type và formatting annotation tốt hơn Unified EL trong một số trường hợp. Nếu ứng dụng cũ chuyển expression parser từ Spring EL sang Unified EL, hãy kiểm tra lại binding và format annotation thay vì chỉ kiểm tra cú pháp EL.

Không nên đổi expression parser toàn hệ thống chỉ để sửa một lỗi format. Trước tiên xác định lỗi nằm ở converter registration, flow-builder-services, annotation hay expression parser.

## 11. Những thay đổi hành vi cần lưu ý khi nâng cấp

Converter mới có thể compile nhưng vẫn thay đổi cách xử lý input. Hãy kiểm tra các trường hợp sau:

| Trường hợp | Câu hỏi cần xác nhận |
| --- | --- |
| `null` | Converter có nhận `null` không? Spring có bỏ qua hay trả `null`? |
| Chuỗi rỗng | `""` trở thành `null`, empty object hay lỗi? |
| Khoảng trắng | Có trim trước khi parse không? |
| Locale | `1,234` có nghĩa một nghìn hai trăm ba mươi tư hay một phẩy hai ba bốn? |
| Case sensitivity | Enum/code có phân biệt hoa thường không? |
| Invalid value | Ném exception nào và hiển thị binding message ra sao? |
| Print ngược | View có thể hiển thị lại giá trị đã bind đúng format không? |
| Collection | Có chuyển từng phần tử và giữ thứ tự không? |
| Generic type | Có xác định đúng kiểu phần tử của collection không? |
| Annotation | `@DateTimeFormat`/`@NumberFormat` có được áp dụng không? |
| Multiple converters | Có nhiều converter cùng source/target gây lựa chọn mơ hồ không? |
| Security | Client có thể bind vào field nhạy cảm ngoài dự kiến không? |

### Required binding không thay thế converter

```xml
<binder>
    <binding property="invoiceDate" required="true" />
</binder>
```

`required="true"` kiểm tra dữ liệu bắt buộc theo binding. Nó không quyết định format ngày và không thay thế formatter. Nếu chuỗi không parse được, đó là conversion/binding error; nếu parse được nhưng ngày không hợp lệ theo nghiệp vụ, đó là validation error.

### Không chuyển lỗi conversion thành giá trị mặc định một cách âm thầm

Ví dụ converter trả `BigDecimal.ZERO` khi chuỗi tiền sai định dạng có thể làm ứng dụng hiểu nhầm người dùng nhập 0 đồng. Hãy trả lỗi conversion để người dùng sửa, trừ khi contract nghiệp vụ quy định rõ giá trị mặc định.

## 12. Lộ trình nâng cấp an toàn theo từng đợt

Không cần thay toàn bộ converter trong một lần. Có thể chia theo rủi ro và mức độ sử dụng.

### Đợt 1 — Lập inventory và chụp hành vi hiện tại

- Tìm tất cả converter, named converter, `PropertyEditor`, `@InitBinder`.
- Liệt kê flow và field sử dụng từng converter.
- Ghi format input/output, locale, empty value và message lỗi.
- Tạo test characterization cho hành vi hiện tại.

### Đợt 2 — Đồng bộ service MVC và Web Flow

- Xác định `applicationConversionService` của MVC.
- Tạo Spring Binding wrapper delegate tới service đó.
- Cấu hình `flow-builder-services` của registry thật.
- Kiểm tra một field trong MVC và một field trong Web Flow dùng cùng formatter.

### Đợt 3 — Chuyển converter không tên có thể chuyển đổi trực tiếp

- Chuyển các converter đơn giản sang Spring Core `Converter`.
- Chuyển parse/print field sang `Formatter`.
- Đăng ký trong conversion service chung.
- Giữ converter legacy không tên ở nơi chưa thể di chuyển và ghi rõ lý do.

### Đợt 4 — Loại bỏ named converter

- Chuyển từng `converter="id"` sang type-based converter/formatter.
- Xóa thuộc tính `converter` khỏi binding.
- Nếu mỗi field có format riêng, dùng annotation/formatter metadata hoặc value object.
- Xóa lời gọi `addConverter("id", ...)` khi không còn tham chiếu.

### Đợt 5 — Chuyển PropertyEditor

- Chuyển editor dùng cho form web sang Formatter.
- Chuyển object-to-object sang Converter.
- Giữ editor trong extension point legacy nếu chưa thể thay và test riêng.
- Không chia sẻ editor mutable giữa request.

### Đợt 6 — Regression và dọn cấu hình

- Chạy test flow và MVC.
- Kiểm tra locale, parse/print, empty value, binding errors.
- Xóa adapter/bean legacy khi không còn converter cũ.
- Xóa import và dependency không cần thiết sau khi xác nhận không còn consumer.
- Cập nhật tài liệu vận hành và quy ước viết converter mới.

### Ví dụ ma trận migration

| Thành phần | Hiện tại | Đích | Tiêu chí hoàn tất |
| --- | --- | --- | --- |
| `customerCode` named converter | `addConverter("customerCode", ...)` | Spring Core `Converter` | Không còn `converter="customerCode"` |
| `LegacyDateEditor` | `@InitBinder` | `Formatter<LocalDate>` | MVC và flow bind cùng format |
| `MoneyConverter` Binding cũ | `addConverter(converter)` | `Formatter<Money>` | Legacy adapter không còn được dùng |
| Enum converter | Custom Binding converter | Spring default hoặc `ConverterFactory` | Case/invalid behavior được kiểm thử |
| Number format | `PropertyEditor` | `@NumberFormat`/Formatter | Locale và parse/print nhất quán |

## 13. Kiểm thử sau khi chuyển đổi

Một migration chỉ hoàn tất khi hành vi được xác nhận ở nơi thực sự dùng conversion service, không chỉ khi unit test converter chạy qua.

### 13.1. Unit test converter

```java
class StringToCustomerCodeConverterTest {

    private final StringToCustomerCodeConverter converter =
            new StringToCustomerCodeConverter();

    @Test
    void trimsCode() {
        assertEquals(
                new CustomerCode("AB-123"),
                converter.convert("  AB-123  "));
    }
}
```

Test converter độc lập kiểm tra quy tắc chuyển đổi và edge cases như `null`, empty, whitespace, input sai.

### 13.2. Test formatter hai chiều

```java
class LocalDateDmyFormatterTest {

    private final LocalDateDmyFormatter formatter =
            new LocalDateDmyFormatter();

    @Test
    void parsesAndPrintsDate() throws ParseException {
        Locale locale = Locale.forLanguageTag("vi-VN");
        LocalDate value = formatter.parse("20/05/2026", locale);

        assertEquals(LocalDate.of(2026, 5, 20), value);
        assertEquals("20/05/2026", formatter.print(value, locale));
    }
}
```

Kiểm thử thêm ngày không hợp lệ, locale khác, chuỗi rỗng và format có/không có số 0 đầu.

### 13.3. Test `ConversionService`

```java
assertTrue(conversionService.canConvert(
        String.class, CustomerCode.class));

CustomerCode code = conversionService.convert(
        "AB-123", CustomerCode.class);

assertEquals(new CustomerCode("AB-123"), code);
```

Với formatter, test cả chiều parse và print thông qua conversion service/formatter registry.

### 13.4. Test Spring Web Flow thực tế

Với flow test:

1. Khởi chạy flow và vào `editCustomer`.
2. Gửi request parameter `customerCode=AB-123`.
3. Xác nhận model nhận `CustomerCode`, không phải `String`.
4. Gửi giá trị sai và xác nhận flow ở lại view với binding error.
5. Xác nhận formatter in giá trị trở lại view đúng format.
6. Xác nhận không còn phụ thuộc named converter trong XML.

### 13.5. Test Spring MVC

Test controller có cùng model/field và cùng conversion service. Nếu MVC và Web Flow trả kết quả khác nhau, kiểm tra service instance, annotation, binder và expression parser.

### 13.6. Test tương thích toàn ứng dụng

| Nhóm | Trường hợp |
| --- | --- |
| Flow | Tất cả flow có `view-state model` và binding tùy chỉnh |
| MVC | Controller dùng `@ModelAttribute`, `@RequestParam`, `@InitBinder` |
| Locale | `vi-VN`, `en-US` và locale ứng dụng hỗ trợ |
| Invalid input | Chuỗi rỗng, khoảng trắng, format sai, giá trị vượt giới hạn |
| Collections | List, Set, array và nested property |
| Date/number | Ngày, giờ, decimal, currency và timezone |
| Security | Không bind field nhạy cảm không được khai báo |
| Error display | Message code, field error và global error |
| Runtime | Không có converter ambiguity hoặc lỗi khởi tạo context |

Đừng chỉ chạy test happy path. Một converter thay thế có thể parse đúng input phổ biến nhưng làm mất thông báo lỗi hoặc thay đổi cách xử lý empty string.

## 14. Các lỗi thường gặp khi nâng cấp

### 14.1. MVC đã có formatter nhưng Web Flow vẫn báo `typeMismatch`

**Nguyên nhân:** Web Flow đang dùng `DefaultConversionService` delegate tới instance khác.

**Khắc phục:** cấu hình `flow-builder-services` để wrapper delegate tới đúng `applicationConversionService` dùng trong MVC.

### 14.2. Named converter không được gọi sau khi chuyển service

**Nguyên nhân:** named converter không thuộc Spring type conversion. Nó chỉ được gọi qua cơ chế tương thích cũ.

**Khắc phục:** chuyển logic sang Spring `Converter`/`Formatter`, đăng ký vào service chung và bỏ `converter="..."`.

### 14.3. Converter cũ đăng ký nhưng không hoạt động

**Nguyên nhân:** gọi nhầm overload `addConverter(String, Converter)` hoặc đăng ký bean vào service không được flow registry sử dụng.

**Khắc phục:** xác định overload, kiểm tra class thực tế của bean và xác nhận `flow-builder-services` tham chiếu đúng service.

### 14.4. Import nhầm hai `DefaultConversionService`

**Nguyên nhân:** dùng class Spring Core thay cho class Spring Binding wrapper hoặc ngược lại.

**Khắc phục:** kiểm tra fully qualified class name. Wrapper của Web Flow nằm trong `org.springframework.binding.convert.service`.

### 14.5. Formatter chỉ parse nhưng không print

**Nguyên nhân:** dùng Converter một chiều cho field cần hiển thị lại trong form.

**Khắc phục:** viết `Formatter<T>` hoặc đăng ký cả hai chiều conversion phù hợp.

### 14.6. Hai formatter cùng xử lý một kiểu

**Nguyên nhân:** formatter global và formatter tùy chỉnh cùng đăng ký cho một target type mà không có quy tắc chọn rõ.

**Khắc phục:** thống nhất format, dùng annotation metadata cho field riêng hoặc tách value object.

### 14.7. PropertyEditor singleton gây lỗi request đồng thời

**Nguyên nhân:** editor có state nội bộ và bị chia sẻ giữa nhiều request.

**Khắc phục:** dùng Formatter thread-safe hoặc tạo PropertyEditor mới theo binder/request nếu buộc giữ API cũ.

### 14.8. Đổi converter làm validation thay đổi

**Nguyên nhân:** chuỗi rỗng, giá trị null hoặc lỗi parse được xử lý khác trước.

**Khắc phục:** characterization test trước migration, test binding error và validation sau migration.

### 14.9. Annotation không hoạt động trong Unified EL

**Nguyên nhân:** ứng dụng dùng expression parser không hỗ trợ đầy đủ tích hợp formatting annotation như Spring EL.

**Khắc phục:** kiểm tra expression parser, conversion service và cấu hình Web Flow trước khi đổi parser.

## 15. Bài tập thực hành

Một ứng dụng CRM cũ có model:

```java
public class CustomerForm {
    private CustomerCode code;
    private LocalDate birthDate;
    private BigDecimal creditLimit;
}
```

Flow XML:

```xml
<view-state id="editCustomer" model="customer">
    <binder>
        <binding property="code"
                 required="true"
                 converter="customerCode" />
        <binding property="birthDate"
                 required="true"
                 converter="legacyDate" />
        <binding property="creditLimit"
                 converter="money" />
    </binder>
</view-state>
```

Spring configuration cũ:

```java
public class CustomerConversionService
        extends DefaultConversionService {

    public CustomerConversionService() {
        addDefaultConverters();
        addDefaultAliases();
        addConverter("customerCode", new CustomerCodeConverter());
        addConverter("legacyDate", new LegacyDateConverter());
        addConverter("money", new MoneyConverter());
    }
}
```

**Nhiệm vụ:**

1. Xác định cả ba converter đang dùng overload named converter.
2. Chọn `Converter<String, CustomerCode>` cho mã khách hàng.
3. Chọn `Formatter<LocalDate>` hoặc `@DateTimeFormat` cho ngày sinh.
4. Chọn `Formatter<BigDecimal>` nếu format tiền phụ thuộc locale.
5. Cấu hình một `FormattingConversionService` dùng chung cho MVC và Web Flow.
6. Xóa `converter="..."` sau khi đã đăng ký converter/formatter mới.
7. Viết test cho `vi-VN`, `en-US`, chuỗi rỗng, input sai và print ngược.
8. Kiểm tra binder chỉ cho phép ba field cần thiết.

**Câu hỏi tự kiểm tra:**

- Vì sao converter cũ không tên có thể tiếp tục hoạt động nhưng named converter lại deprecated?
- `DefaultConversionService` trong `org.springframework.binding.convert.service` khác gì class cùng tên trong Spring Core?
- Vì sao `Formatter` phù hợp hơn `Converter` cho ngày và số tiền nhập từ form?
- Vì sao chỉ cấu hình `<mvc:annotation-driven>` chưa bảo đảm Web Flow dùng cùng formatter?
- Khi nào nên giữ một Spring Binding converter tạm thời qua adapter?

## 16. Ghi nhớ

- Spring Web Flow sử dụng Spring type conversion/formatting cho gần như mọi nhu cầu chuyển đổi từ phiên bản 2.1.
- `org.springframework.binding.convert.converters.Converter` và `org.springframework.core.convert.converter.Converter` là hai interface khác nhau.
- Converter Spring Binding đăng ký bằng `addConverter(converter)` có thể được adapter sang Spring `GenericConverter`.
- Named converter đăng ký bằng `addConverter("id", converter)` và dùng qua `<binding converter="id"/>` là cơ chế legacy, deprecated và không tham gia Spring type conversion.
- `DefaultConversionService` của Spring Binding là wrapper cho Web Flow; có thể delegate tới Spring `FormattingConversionService`.
- Nên dùng chung `applicationConversionService` cho Spring MVC và Web Flow thông qua `flow-builder-services`.
- Dùng Spring Core `Converter` cho object-to-object; dùng `Formatter` cho parse/print chuỗi theo locale.
- `PropertyEditor` là API cũ, mutable; nếu phải giữ, hãy giới hạn vòng đời theo binder/request.
- Di chuyển từng bước: inventory → chia sẻ conversion service → chuyển converter → bỏ named binding → chuyển editor → regression.
- Kiểm thử cả MVC và flow, parse/print, locale, empty input, binding error và security allow-list.

### Tài liệu tham khảo

- [Spring Web Flow 3.0.2 Reference Guide — Upgrading to Spring 3 Type Conversion and Formatting](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/#upgrading-to-spring-3-type-conversion-and-formatting): converter cũ, named converter và khuyến nghị migration.
- [Spring Web Flow 3.0.2 Reference Guide — Configuring Type Conversion and Formatting](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/#configuring-type-conversion-and-formatting): chia sẻ `FormattingConversionService` giữa MVC và Web Flow.
- [Spring Web Flow 3.0.1 API — `GenericConversionService`](https://docs.spring.io/spring-webflow/docs/3.0.1/api/org/springframework/binding/convert/service/GenericConversionService.html): adapter cho converter Spring Binding và khác biệt overload named converter.
- [Spring Web Flow 3.0.1 API — Spring Binding `Converter`](https://docs.spring.io/spring-webflow/docs/3.0.1/api/org/springframework/binding/convert/converters/Converter.html): chữ ký và contract converter cũ.
- [Spring Framework Reference — Spring Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html): `Converter`, `Formatter`, `ConversionService` và format theo locale.
- [Spring Framework Reference — Configuring a Global Date and Time Format](https://docs.spring.io/spring-framework/reference/core/validation/format-configuring-formatting-globaldatetimeformat.html): cấu hình formatter ngày giờ toàn cục.
