# CustomEditorConfigurer trong cấu hình bean của Spring Framework

## 1. Vấn đề: từ chuỗi cấu hình thành thuộc tính Java có kiểu

Trong Spring IoC container, một bean thường nhận các property qua định nghĩa bean. Ví dụ, file XML có thể ghi `<property name="currency" value="usd"/>`. Giá trị nguồn là chuỗi `"usd"`, nhưng setter của bean lại cần một đối tượng `CurrencyCode`. Spring phải **chuyển đổi kiểu** trước khi gọi setter.

Nếu đây là kiểu do ứng dụng tự tạo và chưa có bộ chuyển đổi tương thích, ta có thể triển khai một JavaBeans `PropertyEditor` và đăng ký cho container bằng **`CustomEditorConfigurer`**.

`CustomEditorConfigurer` nằm trong package `org.springframework.beans.factory.config`, implements `BeanFactoryPostProcessor` và `Ordered`. Nó giúp đăng ký custom `PropertyEditor` với `BeanFactory` để container dùng trong **quá trình tạo và cấu hình bean**. Những editor này tham gia cơ chế JavaBeans property conversion bên trong container.

Ví dụ minh họa:

```text
Bean definition:
    currency = " usd "
          |
          v
Spring ApplicationContext
    + CustomEditorConfigurer
          |
          v
PropertyEditor<CurrencyCode>
  " usd " -> CurrencyCode("USD")
          |
          v
BeanWrapper / property population
          |
          v
PaymentSettings.setCurrency(CurrencyCode("USD"))
```

**Điểm cốt lõi của chủ đề:** `CustomEditorConfigurer` cấu hình chuyển đổi cho **bean creation** trong container. Nó **không tự động đăng ký editor cho mọi `DataBinder` hoặc `WebDataBinder` xử lý form/HTTP request**. Nếu cần dùng cùng editor ở tầng web, phải đăng ký tại binder thích hợp, thường thông qua một `PropertyEditorRegistrar` có thể tái sử dụng.

## 2. Các thành phần và ranh giới trách nhiệm

| Thành phần | Vai trò | Phạm vi |
| --- | --- | --- |
| `java.beans.PropertyEditor` | Đọc/ghi giá trị và chuyển `String` thành kiểu Java cụ thể qua `setAsText(...)` | Một editor, có trạng thái |
| `PropertyEditorSupport` | Lớp tiện ích để tạo editor; giữ giá trị qua `setValue(...)`/`getValue()` | Mỗi instance editor |
| `PropertyEditorRegistry` | API `registerCustomEditor(...)` gắn editor với một kiểu hoặc đường dẫn property | BeanWrapper hoặc DataBinder cụ thể |
| `PropertyEditorRegistrar` | Đóng gói logic tạo và đăng ký các editor trên registry được truyền vào | Dùng lại cho nhiều registry |
| `CustomEditorConfigurer` | `BeanFactoryPostProcessor` đăng ký editor/registrar vào bean factory | Bean creation của một IoC container |
| `BeanWrapper` | Chuyển đổi và ghi các property bean khi populate | Một target bean |
| `DataBinder` / `WebDataBinder` | Nhận dữ liệu đầu vào, chuyển kiểu, bind, gom lỗi | Binding của object/request |
| `ConversionService` / `Converter` | Cơ chế chuyển đổi kiểu hiện đại, dễ chia sẻ và thường stateless | Nhiều ngữ cảnh khi được tích hợp |

Một luồng cấu hình bean khác luồng xử lý request:

```text
A. Spring container:
   ApplicationContext.refresh()
     -> BeanFactoryPostProcessor (CustomEditorConfigurer)
     -> đăng ký editor/registrar vào BeanFactory
     -> BeanFactory tạo PaymentSettings
     -> PropertyEditor chuyển giá trị string
     -> setter nhận CurrencyCode

B. HTTP form:
   Request
     -> WebDataBinder
     -> các editor đã được đăng ký TRÊN binder
     -> bind vào model attribute
     -> BindingResult/validation
     -> controller

A không tự động đăng ký editor cho B.
Có thể tái sử dụng cùng PropertyEditorRegistrar ở hai nơi.
```

`CustomEditorConfigurer` không phải một `@Component` làm business logic, không phải `BeanPostProcessor` chạy sau mỗi setter và không phải trình quản lý tất cả `Converter` toàn ứng dụng. Việc chạy sớm thuộc lifecycle `BeanFactoryPostProcessor`.

## 3. API quan trọng của `CustomEditorConfigurer`

Các phương thức cấu hình thường dùng:

```java
CustomEditorConfigurer configurer = new CustomEditorConfigurer();

configurer.setPropertyEditorRegistrars(
    new PropertyEditorRegistrar[] { new CurrencyCodeRegistrar() }
);

// Hoặc đăng ký lớp editor cho kiểu Java:
Map<Class<?>, Class<? extends PropertyEditor>> customEditors =
    Map.of(CurrencyCode.class, CurrencyCodeEditor.class);

configurer.setCustomEditors(customEditors);
```

Đây là **fragment minh họa**, giả định các lớp `CurrencyCode`, `CurrencyCodeRegistrar` và `CurrencyCodeEditor` tồn tại và có import tương ứng.

### 3.1. `setPropertyEditorRegistrars(...)`

Tham số là mảng `PropertyEditorRegistrar[]`. Mỗi registrar triển khai:

```java
@Override
public void registerCustomEditors(PropertyEditorRegistry registry) {
    registry.registerCustomEditor(
        CurrencyCode.class,
        new CurrencyCodeEditor()
    );
}
```

Ở đây, registrar **tạo một editor mới** khi được áp dụng cho một registry. Spring khuyến nghị phương án này vì editor JavaBeans có trạng thái (ví dụ `PropertyEditorSupport` giữ `getValue()`) và không nên vô tình chia sẻ cùng editor instance giữa các bean/request song song.

Một registrar có thể đăng ký **nhiều editor**, chẳng hạn `CurrencyCodeEditor` và `LocaleTagEditor`. Nó còn có thể dùng lại khi cấu hình `DataBinder`, vì cả binder lẫn BeanWrapper đều cung cấp API của `PropertyEditorRegistry` theo cơ chế thích hợp.

### 3.2. `setCustomEditors(...)`

Đây là cách mô tả bản đồ **kiểu đích → lớp editor**, không phải kiểu đích → đối tượng editor đã được tạo:

```java
Map<Class<?>, Class<? extends PropertyEditor>> editorTypes =
    new HashMap<>();

editorTypes.put(CurrencyCode.class, CurrencyCodeEditor.class);
configurer.setCustomEditors(editorTypes);
```

Điều quan trọng:

- Key là `Class<?>` của **kiểu cần chuyển đổi** (`CurrencyCode.class`).
- Value là `Class<? extends PropertyEditor>` của **lớp editor** (`CurrencyCodeEditor.class`).
- Editor phải có khả năng được container khởi tạo thích hợp, thường cần constructor không tham số truy cập được.
- Đừng đưa một singleton `new CurrencyCodeEditor()` vào map này; vừa không khớp kiểu method, vừa dễ tạo rủi ro dùng chung trạng thái editor.
- Nếu editor cần dependency hoặc phải tạo bằng logic đặc biệt, dùng `PropertyEditorRegistrar` để kiểm soát việc khởi tạo.

Ở cấu hình XML, có thể dùng tên class dưới dạng chuỗi và để Spring resolve kiểu. Trong Java code, map phải dùng object `Class` như chữ ký đã khai báo.

### 3.3. `setOrder(...)`

Configurer thực thi `Ordered` nên có thể thiết lập độ ưu tiên khi có nhiều `BeanFactoryPostProcessor`:

```java
configurer.setOrder(100);
```

Thứ tự không thay thế quy tắc xung đột giữa các editor. Nếu nhiều cấu hình cùng đăng ký cho một kiểu, nên thống nhất trách nhiệm và kiểm thử editor thực tế được sử dụng. Không dùng order như cách tùy tiện giải quyết việc thiết kế trùng lặp.

## 4. Tạo một `PropertyEditor` cho kiểu ứng dụng

Giả sử ứng dụng muốn lưu mã tiền tệ là giá trị chuẩn hóa ba chữ cái in hoa, ví dụ `"usd"` → `CurrencyCode("USD")`.

Model:

```java
public record CurrencyCode(String value) {}
```

Đây là một record chứa dữ liệu. Record tự nó **không** dạy Spring chuyển chuỗi `"usd"` thành record; cần conversion phù hợp nếu bean definition cung cấp `String` mà setter nhận `CurrencyCode`.

Editor:

```java
public class CurrencyCodeEditor extends PropertyEditorSupport {

    @Override
    public void setAsText(String text) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException(
                "Mã tiền tệ không được để trống"
            );
        }

        String code = text.strip().toUpperCase(Locale.ROOT);

        if (!code.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                "Mã tiền tệ phải gồm đúng ba chữ cái"
            );
        }

        setValue(new CurrencyCode(code));
    }

    @Override
    public String getAsText() {
        CurrencyCode value = (CurrencyCode) getValue();
        return value == null ? "" : value.value();
    }
}
```

Đây là đoạn code mô tả lớp editor, cần import `java.beans.PropertyEditorSupport` và `java.util.Locale`, cùng lớp `CurrencyCode`. Với đầu vào `" usd "`, `setAsText` loại khoảng trắng, đổi thành uppercase và gọi `setValue` lưu `CurrencyCode("USD")`.

`getAsText` chuyển ngược giá trị hiện có sang chuỗi, hữu ích cho các tình huống đọc/hiển thị, nhưng không phải mọi luồng bean creation đều tự gọi nó.

**Không dùng `setAsText` để thực hiện truy vấn database tốn thời gian hoặc side effect nghiệp vụ** trong quá trình khởi tạo bean. Khi editor gặp input sai định dạng, ném ngoại lệ có giải thích; container thường gói lỗi vào exception bean creation, còn binder có thể ghi nhận lỗi conversion trong `BindingResult` tùy trường hợp.

## 5. Tại sao `PropertyEditorRegistrar` thường được ưu tiên?

Một registrar gói logic đăng ký cho nhiều registry:

```java
public final class CurrencyCodeRegistrar
        implements PropertyEditorRegistrar {

    @Override
    public void registerCustomEditors(PropertyEditorRegistry registry) {
        registry.registerCustomEditor(
            CurrencyCode.class,
            new CurrencyCodeEditor()
        );
    }
}
```

Đây là fragment, cần import `org.springframework.beans.PropertyEditorRegistrar` và `org.springframework.beans.PropertyEditorRegistry`.

Dùng registrar có ba lợi ích trực tiếp:

1. **Tạo editor mới theo lần đăng ký.** `PropertyEditorSupport` giữ state nội bộ; một editor đã xử lý `"USD"` có thể đang giữ một `CurrencyCode`. Không nên dùng chung vô kiểm soát giữa thread hoặc request.
2. **Tái sử dụng logic đăng ký.** Cùng registrar có thể phục vụ bean factory và một `WebDataBinder` cụ thể mà không phải sao chép `registry.registerCustomEditor(...)`.
3. **Giữ việc chuyển đổi tách khỏi business class.** Model biết kiểu `CurrencyCode`; registrar tập trung vào cách chuyển từ dữ liệu cấu hình vào kiểu đó.

Với cơ chế `PropertyEditorRegistrar`, mỗi lần registry áp dụng registrar, code tạo editor mới. Không nên khẳng định cứ mỗi field được set thì lại có một instance editor mới; vòng đời cụ thể của registry/BeanWrapper có thể bao trùm nhiều thao tác chuyển đổi trong một lượt tạo bean.

## 6. Ví dụ Java 17 đầy đủ chạy với `ApplicationContext`

Ví dụ sau sử dụng Spring `AnnotationConfigApplicationContext` và **định nghĩa bean bằng `RootBeanDefinition`**. Ta khai báo hai bean `PaymentSettings` nhận chuỗi cấu hình khác nhau, đồng thời đăng ký `CustomEditorConfigurer` làm `BeanFactoryPostProcessor`. Khi context refresh, converter được kích hoạt trong quá trình Spring populate property.

Đây là ví dụ **bean-definition conversion thật**, không phải việc Java tự gọi `new CurrencyCode(...)` trong method tạo bean.

### 6.1. Cấu trúc thư mục

```text
custom-editor-demo/
├── pom.xml
└── src/main/java/example/CustomEditorDemo.java
```

File `pom.xml` (Java 17, Spring Framework 6.2.14):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>custom-editor-demo</artifactId>
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
          <mainClass>example.CustomEditorDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

File `src/main/java/example/CustomEditorDemo.java`:

```java
package example;

import java.beans.PropertyEditorSupport;
import java.util.Locale;

import org.springframework.beans.PropertyEditorRegistrar;
import org.springframework.beans.PropertyEditorRegistry;
import org.springframework.beans.factory.config.CustomEditorConfigurer;
import org.springframework.beans.factory.support.RootBeanDefinition;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class CustomEditorDemo {

    public record CurrencyCode(String value) {}

    public static class CurrencyCodeEditor extends PropertyEditorSupport {

        @Override
        public void setAsText(String text) {
            if (text == null || text.isBlank()) {
                throw new IllegalArgumentException(
                    "Currency code must not be blank"
                );
            }
            String normalized =
                text.strip().toUpperCase(Locale.ROOT);

            if (!normalized.matches("[A-Z]{3}")) {
                throw new IllegalArgumentException(
                    "Currency code must contain three letters"
                );
            }
            setValue(new CurrencyCode(normalized));
        }

        @Override
        public String getAsText() {
            CurrencyCode code = (CurrencyCode) getValue();
            return code == null ? "" : code.value();
        }
    }

    public static class CurrencyCodeRegistrar
            implements PropertyEditorRegistrar {

        @Override
        public void registerCustomEditors(
                PropertyEditorRegistry registry) {
            registry.registerCustomEditor(
                CurrencyCode.class,
                new CurrencyCodeEditor()
            );
        }
    }

    public static class PaymentSettings {

        private CurrencyCode currency;

        public PaymentSettings() {}

        public CurrencyCode getCurrency() {
            return currency;
        }

        public void setCurrency(CurrencyCode currency) {
            this.currency = currency;
        }
    }

    public static void main(String[] args) {

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            RootBeanDefinition configurerDefinition =
                new RootBeanDefinition(CustomEditorConfigurer.class);

            configurerDefinition.getPropertyValues().add(
                "propertyEditorRegistrars",
                new PropertyEditorRegistrar[] {
                    new CurrencyCodeRegistrar()
                }
            );

            context.registerBeanDefinition(
                "customEditorConfigurer",
                configurerDefinition
            );

            RootBeanDefinition first =
                new RootBeanDefinition(PaymentSettings.class);
            first.getPropertyValues().add("currency", " usd ");

            RootBeanDefinition second =
                new RootBeanDefinition(PaymentSettings.class);
            second.getPropertyValues().add("currency", " eur ");

            context.registerBeanDefinition("first", first);
            context.registerBeanDefinition("second", second);

            context.refresh();

            PaymentSettings firstBean =
                context.getBean("first", PaymentSettings.class);
            PaymentSettings secondBean =
                context.getBean("second", PaymentSettings.class);

            System.out.println(
                "first=" + firstBean.getCurrency().value()
            );
            System.out.println(
                "second=" + secondBean.getCurrency().value()
            );
        }
    }
}
```

Chạy ở thư mục có `pom.xml`:

```bash
mvn -q compile exec:java
```

Kết quả nghiệp vụ mong đợi trên `stdout` (không tính log tải dependencies hoặc cảnh báo Maven nếu môi trường có):

```text
first=USD
second=EUR
```

**Giải thích chính xác điều gì diễn ra:**

- `CustomEditorConfigurer` được khai báo bằng một `RootBeanDefinition` có property `propertyEditorRegistrars`. Vì nó là `BeanFactoryPostProcessor`, context sẽ gọi để đăng ký editor với bean factory trong `refresh()`.
- `first` và `second` đều là `PaymentSettings` với property `currency` khai báo bằng chuỗi thô. Spring nhìn thấy setter cần `CurrencyCode` nên dùng editor đã đăng ký.
- `CurrencyCodeEditor.setAsText` biến `" usd "` thành `CurrencyCode("USD")` và tương tự cho `" eur "`.
- Mã chạy chỉ có **một public top-level class `CustomEditorDemo`**; các loại còn lại là nested public static nên có thể lưu trong một file `CustomEditorDemo.java`.
- Spring `spring-context` kéo theo các module `spring-beans`, `spring-core` cần thiết.
- Không có database, HTTP request, `@Controller` hoặc `DataBinder` trong ví dụ. Chính bean factory thực hiện conversion khi tạo bean.

Nếu thay `" usd "` bằng `"invalid-code"`, editor ném `IllegalArgumentException` và việc khởi tạo bean có thể thất bại, tạo bean creation exception. Không nên gắn kết chắc chắn message exception cụ thể với một phiên bản nếu chưa kiểm tra cause chain.

## 7. Cấu hình qua `@Bean` trong ứng dụng dùng Java configuration

Trong một ứng dụng Spring quản lý cấu hình bằng annotation, có thể khai báo configurer như một `@Bean`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.PropertyEditorRegistrar;
import org.springframework.beans.factory.config.CustomEditorConfigurer;

@Configuration(proxyBeanMethods = false)
public class EditorConfiguration {

    @Bean
    public static CustomEditorConfigurer customEditorConfigurer() {
        CustomEditorConfigurer configurer =
            new CustomEditorConfigurer();

        configurer.setPropertyEditorRegistrars(
            new PropertyEditorRegistrar[] {
                new CurrencyCodeRegistrar()
            }
        );
        return configurer;
    }
}
```

Đây là đoạn code **tích hợp**: cần `CurrencyCodeRegistrar` ở package/import tương ứng và `EditorConfiguration` được application context scan hoặc đăng ký. Nên để `@Bean` trả `BeanFactoryPostProcessor` là **static method** để được tạo đủ sớm mà không phải khởi tạo sớm toàn bộ `@Configuration` instance; cách khai báo static là khuyến nghị phổ biến cho các bean thuộc nhóm hậu xử lý factory.

Ví dụ này chỉ **đăng ký editor với container**. Muốn chứng minh conversion, phải có một bean mà container thực sự populate property từ `String` sang kiểu `CurrencyCode`. Nếu gọi Java:

```java
@Bean
PaymentSettings paymentSettings() {
    PaymentSettings settings = new PaymentSettings();
    settings.setCurrency(new CurrencyCode("USD"));
    return settings;
}
```

thì ta đã tự tạo `CurrencyCode`, editor không cần được gọi. Đừng lấy kết quả của đoạn này làm bằng chứng `CustomEditorConfigurer` hoạt động.

### 7.1. XML configuration với `propertyEditorRegistrars`

Dành cho ứng dụng dùng Spring XML:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
          http://www.springframework.org/schema/beans
          https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean class="org.springframework.beans.factory.config.CustomEditorConfigurer">
        <property name="propertyEditorRegistrars">
            <list>
                <bean class="example.CurrencyCodeRegistrar"/>
            </list>
        </property>
    </bean>

    <bean id="paymentSettings" class="example.PaymentSettings">
        <property name="currency" value="usd"/>
    </bean>
</beans>
```

Đây là **mẫu XML độc lập theo kiểu top-level classes**, giả định `example.CurrencyCodeRegistrar` và `example.PaymentSettings` có class public đúng tên và setter như đã mô tả. Với demo ở mục 6 là nested classes, muốn dùng trực tiếp phải khai báo tên class JVM chứa ký hiệu `$` (ví dụ `example.CustomEditorDemo$PaymentSettings`) hoặc tách các class ra file riêng.

Ứng dụng cấu hình XML cần load file này bằng `ClassPathXmlApplicationContext` hoặc một context tương ứng. Nếu mọi class/bean được định nghĩa hợp lệ, `currency` trong `paymentSettings` nhận đối tượng được chuyển từ chuỗi `"usd"`.

### 7.2. XML với `customEditors`

Một cách khác là khai báo **lớp editor** theo kiểu:

```xml
<bean class="org.springframework.beans.factory.config.CustomEditorConfigurer">
    <property name="customEditors">
        <map>
            <entry key="example.CurrencyCode"
                   value="example.CurrencyCodeEditor"/>
        </map>
    </property>
</bean>
```

Cần class `example.CurrencyCodeEditor` triển khai `PropertyEditor` và có constructor phù hợp. Giá trị `value` trong XML là **tên lớp**, không phải một đối tượng editor singleton đã dùng từ trước.

Nếu editor cần dependency, số lượng editor nhiều hoặc phải tái sử dụng ở những loại binder khác, ưu tiên `PropertyEditorRegistrar`.

## 8. Vì sao không được dùng một editor instance như singleton chung?

`PropertyEditorSupport` giữ state của lần chuyển đổi qua `setValue()`/`getValue()`, đôi khi còn giữ định dạng/ngữ cảnh. Nếu hai request hoặc hai bean cùng dùng một editor instance mà không được quản lý concurrency, giá trị có thể bị ghi đè ngoài ý muốn.

Sai lầm về thiết kế:

```java
// Minh họa kiểu chia sẻ editor cần tránh:
private static final CurrencyCodeEditor SHARED =
    new CurrencyCodeEditor();

void configure(PropertyEditorRegistry registry) {
    registry.registerCustomEditor(CurrencyCode.class, SHARED);
}
```

Đoạn này **không phải thành phần runnable độc lập**: nó minh họa một editor instance static sẽ bị gắn vào nhiều registry. Không nên viết registrar kiểu đó.

Đúng hướng:

```java
@Override
public void registerCustomEditors(PropertyEditorRegistry registry) {
    registry.registerCustomEditor(
        CurrencyCode.class,
        new CurrencyCodeEditor()
    );
}
```

Registrar có thể bản thân được lưu như một singleton không mang state biến đổi, còn mỗi lần đăng ký vào registry thì tạo editor mới. Từ đó tránh cần đồng bộ `PropertyEditorSupport` ở mức global.

Không suy luận rằng editor luôn hoàn toàn thread-safe chỉ vì đặt trong `CustomEditorConfigurer`. Khi sử dụng editor trong phạm vi application context, phải hiểu công cụ nào tạo instance và khi nào reuse.

## 9. Ranh giới quan trọng: container bean creation và HTTP data binding

Theo Javadoc Spring, editor đăng ký qua `CustomEditorConfigurer` **không tự áp dụng cho data binding**. Đăng ký cho BeanFactory phục vụ bean definitions, còn `DataBinder`/`WebDataBinder` có registry riêng.

Ví dụ một controller có request:

```text
POST /payments
Content-Type: application/x-www-form-urlencoded

currency=usd
```

Nếu handler nhận:

```java
@PostMapping("/payments")
public String submit(
    @ModelAttribute("paymentForm") PaymentForm form,
    BindingResult errors
) {
    if (errors.hasErrors()) {
        return "payment-form";
    }
    return "saved";
}
```

thì dù bean `CustomEditorConfigurer` đã có trong context, **không được mặc nhiên trông chờ** editor đó được áp dụng cho property `PaymentForm.currency`. Cần cấu hình binding ở MVC.

### 9.1. Tái sử dụng registrar bằng `@InitBinder`

Ví dụ code tích hợp:

```java
import org.springframework.beans.PropertyEditorRegistrar;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

@InitBinder("paymentForm")
public void configurePaymentForm(WebDataBinder binder) {
    currencyCodeRegistrar.registerCustomEditors(binder);
}
```

Ở đây `currencyCodeRegistrar` là field/dependency kiểu `PropertyEditorRegistrar` đã được ứng dụng cung cấp, thường chính là registrar được tái sử dụng. `WebDataBinder` triển khai khả năng đăng ký custom editor thông qua API `DataBinder`.

Cũng có thể đăng ký trực tiếp:

```java
@InitBinder("paymentForm")
public void configurePaymentForm(WebDataBinder binder) {
    binder.registerCustomEditor(
        CurrencyCode.class,
        new CurrencyCodeEditor()
    );
}
```

Hai snippet là **hai phương án thay thế**, không thể đặt song song cùng một signature trong controller. Nếu một controller dùng cả hai trong cùng lớp, sẽ trùng method signature và không biên dịch.

`PaymentForm` phải có property/constructor phù hợp, `CurrencyCode` và editor có phạm vi truy cập thích hợp, và `BindingResult` phải nằm ngay sau tham số `@ModelAttribute`. `@InitBinder` tự nó không validate quyền sửa dữ liệu; bean validation hay business validation vẫn cần được chạy theo contract.

### 9.2. Binding ngoài MVC

`DataBinder` trong Spring Core có thể dùng chung registrar:

```java
PaymentForm target = new PaymentForm();
DataBinder binder = new DataBinder(target, "paymentForm");

new CurrencyCodeRegistrar().registerCustomEditors(binder);

MutablePropertyValues params = new MutablePropertyValues();
params.add("currency", "usd");

binder.bind(params);
BindingResult result = binder.getBindingResult();
```

Đây là **fragment cần các class và import phù hợp**. Nó minh họa đăng ký trực tiếp cho binder: không cần và không sử dụng bean `CustomEditorConfigurer`. `PaymentForm` cần getter/setter của `CurrencyCode` hoặc chế độ binding phù hợp. Kết quả thành công là property `currency` nhận `CurrencyCode("USD")`; khi không chuyển đổi được, inspect `result.getFieldErrors()`. Bản thân việc tạo `CustomEditorConfigurer` không thay thế lời gọi `registerCustomEditor(...)` trong trường hợp này.

### 9.3. Việc dùng `@RequestBody` có khác không?

Có. Khi xử lý JSON như:

```json
{"currency": "usd"}
```

`@RequestBody` thường dựa vào Jackson/`HttpMessageConverter` để deserialize body thành object. Một JavaBeans `PropertyEditor` đăng ký với bean factory **không tự cấu hình** Jackson. Nếu cần chuyển đổi chuỗi JSON thành custom type, dùng cơ chế phù hợp của JSON mapper/deserializer hoặc cấu hình serialization riêng.

## 10. `ConversionService`: khi nào nên dùng cơ chế hiện đại hơn?

Spring hỗ trợ cả `PropertyEditor` lịch sử của JavaBeans và API `Converter<S,T>`, `ConverterFactory`, `GenericConverter` với `ConversionService`. Trong ứng dụng mới, nếu nhiệm vụ chỉ là biến đổi giá trị từ `String` thành một kiểu khác và không cần semantics của JavaBeans editor, `Converter` thường rõ ràng và dễ kiểm thử hơn.

Ví dụ:

```java
import org.springframework.core.convert.converter.Converter;

public final class CurrencyCodeConverter
        implements Converter<String, CurrencyCode> {

    @Override
    public CurrencyCode convert(String source) {
        String code =
            source.strip().toUpperCase(Locale.ROOT);

        if (!code.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                "Invalid currency code"
            );
        }
        return new CurrencyCode(code);
    }
}
```

Đây là **fragment**; cần `CurrencyCode` và `Locale`, cùng việc đăng ký converter với đúng `ConversionService`. Converter dạng này không lưu `getValue()` state như `PropertyEditorSupport`, nên dễ dùng chung nếu implementation stateless.

Có thể đăng ký:

- Với bean factory: `ConfigurableBeanFactory.setConversionService(...)` hoặc cấu hình conversion service thích hợp ở context.
- Với Spring MVC: `WebMvcConfigurer.addFormatters(FormatterRegistry registry)` cho converter/formatter phục vụ binding request.
- Với Spring Boot: theo cơ chế conversion/formatter mà module cụ thể dùng; **không** suy luận mọi `ConversionService` ở các tầng đều là một instance và nhận cùng registration.

Việc chuyển sang `Converter` không bắt buộc loại bỏ mọi legacy `PropertyEditor`. Khi một framework hoặc bean definition yêu cầu JavaBeans editor, `CustomEditorConfigurer` vẫn là công cụ hữu ích.

## 11. Lifecycle và cách debug

### 11.1. Vì sao `BeanFactoryPostProcessor` phải có sớm?

Bean factory phải biết cách chuyển giá trị **trước khi tạo các bean phụ thuộc vào editor**. `CustomEditorConfigurer.postProcessBeanFactory(...)` chạy sau khi bean definitions đã được nạp và trước phần tạo bean singleton thông thường. Vì vậy, trong ApplicationContext, khai báo nó như một bean thuộc loại `BeanFactoryPostProcessor` là cách phù hợp để container tự phát hiện.

Nếu ứng dụng dùng `BeanFactory` mức thấp mà không chạy lifecycle của `ApplicationContext`, việc chỉ tạo bean definition của configurer chưa đảm bảo processor được thực thi. Phải bảo đảm khâu đăng ký và thực thi `BeanFactoryPostProcessor` tương ứng trước khi tạo bean mục tiêu.

### 11.2. Phân biệt lỗi không tìm thấy editor với lỗi định dạng

Nếu Spring không biết chuyển `String` sang `CurrencyCode`, có thể gặp `TypeMismatchException` hoặc exception bean creation liên quan conversion. Nếu editor có mặt nhưng chuỗi `"xxx-too-long"` không đạt pattern ba ký tự, lỗi phát sinh từ `setAsText`. Hãy xem cause chain, tên property và giá trị cấu hình; không đánh đồng mọi lỗi thành “bean chưa được scan”.

Các bước debug hữu ích:

1. Xác nhận `CustomEditorConfigurer` được đăng ký trong **đúng application context** quản lý bean đích.
2. Xác nhận kiểu property trong setter chính là `CurrencyCode`; tên class hoặc classloader khác có thể khiến registry không khớp.
3. Kiểm tra registrar thực sự đăng ký `CurrencyCode.class` với instance editor mới.
4. Kiểm tra property value thực sự đến dưới dạng chuỗi từ bean definition; nếu đã là `CurrencyCode`, editor không cần được gọi.
5. Kiểm tra lỗi trong `setAsText`; log nguyên nhân an toàn nhưng tránh rò rỉ dữ liệu nhạy cảm.
6. Nếu đang debug request form, kiểm tra `@InitBinder`/`DataBinder` hoặc `ConversionService` ở tầng MVC, vì configurer của BeanFactory không tự áp dụng.
7. Nếu đang debug JSON, kiểm tra mapper/deserializer của `@RequestBody`.
8. Nếu có nhiều context cha/con, xác định bean factory nào tạo bean và post-processor đăng ký ở context nào.

### 11.3. Constructor injection và `@Bean` method có luôn kích hoạt editor không?

Không. `CustomEditorConfigurer` được dùng khi **bean factory** cần chuyển property value ở đường tạo bean. Với `@Bean` method tự viết `return new PaymentSettings(new CurrencyCode("USD"))`, Java đã tạo đúng kiểu, không có bước chuyển `String` sang `CurrencyCode`. Trong các dạng constructor argument ở bean definition, conversion của factory cũng có thể tham gia nếu thực sự có giá trị thô cần chuyển, nhưng cần kiểm thử đường tạo bean cụ thể.

### 11.4. Nhiều cách đăng ký cùng lúc

Nếu cùng một kiểu `CurrencyCode` được đăng ký bởi editor class map, registrar và conversion service, cơ chế chọn converter/editor phụ thuộc ngữ cảnh, kiểu/property path và cách Spring giải quyết conversion. Tránh tạo nhiều định nghĩa chuyển đổi mâu thuẫn. Có một nguồn đăng ký rõ ràng cho từng boundary giúp dễ quan sát và kiểm thử hơn.

## 12. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Nhét object `PropertyEditor` vào `customEditors` | Sai loại mapping, dễ chia sẻ editor state | Dùng `Class<? extends PropertyEditor>` hoặc `PropertyEditorRegistrar` |
| Editor không có cách khởi tạo phù hợp | Container có thể không tạo được editor | Dùng class editor có constructor hợp lệ hoặc registrar chủ động tạo instance |
| Registrar giữ một editor singleton dùng đi dùng lại | Lẫn giá trị giữa các lượt chuyển đổi, rủi ro concurrency | `new Editor()` trong `registerCustomEditors` |
| Chỉ cấu hình `CustomEditorConfigurer` rồi kỳ vọng MVC tự bind được | `WebDataBinder` không có editor như mong muốn | Đăng ký với `@InitBinder` hoặc MVC conversion service |
| Dùng editor cho JSON `@RequestBody` | Jackson không dùng editor của BeanFactory theo mặc định | Dùng JSON deserializer/mapper phù hợp |
| Không kiểm tra input trong `setAsText` | Giá trị sai định dạng lọt vào bean | Validate cú pháp và ném exception thích hợp |
| Tạo bean bằng Java với giá trị đúng kiểu rồi tưởng editor đã chạy | Test không kiểm chứng conversion | Dùng bean definition có `String` property và kiểm tra kết quả |
| Khai báo `@Bean` non-static cho factory post-processor mà không cân nhắc lifecycle | Cấu hình có thể bị khởi tạo sớm không mong muốn | Ưu tiên static `@Bean` cho `BeanFactoryPostProcessor` |
| Chỉ dựa vào editor để kiểm tra quyền của người dùng | Editor chỉ chuyển kiểu, không authorize | Service kiểm tra quyền/trạng thái và validation nghiệp vụ |
| Đăng ký trong context khác | Bean đích không thấy editor | Xác định đúng context và bean factory chịu trách nhiệm |
| Dùng lớp editor có biến static mutable chia sẻ | State bị trộn giữa request/bean | Editor mới per registry, tránh global mutable state |

## 13. Checklist khi triển khai trong dự án

- Kiểu đích của bean đã rõ? Có cần đổi chuỗi từ bean definition sang custom class không?
- `CustomEditorConfigurer` được khai báo như `BeanFactoryPostProcessor` trong đúng context?
- Có thể dùng một `PropertyEditorRegistrar` tái sử dụng thay vì nhiều map editor khó quản lý?
- Registrar tạo editor mới cho từng registry hay vô tình chia sẻ editor có state?
- `setAsText` có chuyển kiểu và báo lỗi hợp lý cho chuỗi rỗng/sai định dạng?
- Setter/constructor của bean đích có phù hợp với property đang cấu hình?
- Bài test tạo bean từ **giá trị String thực sự**, không tự tạo sẵn object đúng kiểu?
- Cần chạy trong bean factory hay HTTP `DataBinder`? Nếu cả hai, đã đăng ký ở hai boundary?
- Có dùng `ConversionService` hiện đại để thay thế editor cho một kiểu conversion đơn giản không?
- Có phân biệt `@RequestBody` JSON với `@ModelAttribute` form trong thiết kế API không?
- Đã thử lỗi converter, lỗi bean creation và trường hợp chạy trong nhiều application context?

## 14. Bài tập tự kiểm tra

### Bài 1. Nhận biết ranh giới

Ứng dụng cấu hình `CustomEditorConfigurer` cho `CurrencyCode`, sau đó một controller nhận `@ModelAttribute PaymentForm` có field `CurrencyCode currency`. Có chắc `currency=usd` tự được bind không?

**Đáp án:** Không. Editor của bean factory không tự áp dụng cho request binder. Đăng ký cùng editor qua `@InitBinder` hoặc cấu hình `ConversionService` ở MVC phù hợp, rồi kiểm thử.

### Bài 2. Chọn phương án đăng ký

Một `TimeZoneEditor` cần tham số constructor và xử lý nhiều mã múi giờ đặc thù. Chọn `customEditors` hay `propertyEditorRegistrars`?

**Đáp án:** `PropertyEditorRegistrar` thích hợp hơn vì có thể tự tạo instance editor với dependency/tham số và đăng ký nó trên registry, tránh yêu cầu factory phải có constructor không tham số.

### Bài 3. Dự đoán kết quả

`CurrencyCodeEditor` dùng `source.strip().toUpperCase(Locale.ROOT)`. Bean definition có `currency=" eur "`, setter nhận `CurrencyCode`. Configurer đã đăng ký hợp lệ. `getCurrency().value()` trả gì?

**Đáp án:** `"EUR"`. Editor chuẩn hóa chuỗi trước khi bean factory gán property.

### Bài 4. Tìm lỗi concurrency

Registrar chứa `private final CurrencyCodeEditor editor = new CurrencyCodeEditor();` và mỗi lần `registerCustomEditors` đều đăng ký cùng instance ấy. Đây có phải phương án nên dùng?

**Đáp án:** Không. `PropertyEditorSupport` mang state; registrar nên tạo `new CurrencyCodeEditor()` mỗi lần đăng ký để không chia sẻ editor giữa các registry.

### Bài 5. Khi nào editor không cần thiết?

`@Bean PaymentSettings paymentSettings() { return new PaymentSettings(new CurrencyCode("USD")); }`. Dù configurer tồn tại, có cần conversion từ `String` sang `CurrencyCode` trong lời gọi này?

**Đáp án:** Không. Java đã tạo object đúng kiểu ngay trong method; để kiểm chứng editor, dùng property value dạng chuỗi trong bean definition.

## 15. Tài liệu tham khảo chính thức

- Spring Framework Javadoc — [`CustomEditorConfigurer`, Spring 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/factory/config/CustomEditorConfigurer.html): `setPropertyEditorRegistrars`, `setCustomEditors`, lifecycle và ghi chú về `DataBinder`.
- Spring Framework Reference — [Data Binding and Custom PropertyEditors](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): chuyển đổi property và đăng ký thêm editor.
- Spring Framework Javadoc — [`PropertyEditorRegistrar`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/PropertyEditorRegistrar.html): cách áp dụng registrar lên `PropertyEditorRegistry`.
- Spring Framework Javadoc — [`PropertyEditorRegistry`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/PropertyEditorRegistry.html): đăng ký editor theo type/path.
- Spring Framework Javadoc — [`ConfigurableBeanFactory`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/config/ConfigurableBeanFactory.html): `addPropertyEditorRegistrar`, `registerCustomEditor`.
- Spring Framework Reference — [Extensibility with BeanFactoryPostProcessor](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html): lifecycle hậu xử lý factory.
- Spring Framework Reference — [Spring MVC @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html): đăng ký editor/converter cho web data binding.
- Spring Framework Reference — [Spring Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): `Converter` và `ConversionService`.
