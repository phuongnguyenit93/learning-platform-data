# ConversionServiceFactoryBean và bean có tên conversionService

Trong Spring Core, `ConversionService` là API trung tâm để chuyển một giá trị từ kiểu này sang kiểu khác. Ứng dụng có thể đăng ký một instance cho toàn bộ `ApplicationContext`, sau đó Spring sử dụng nó khi cần chuyển đổi dữ liệu; các bean khác cũng có thể inject và gọi trực tiếp service đó.

Trong cấu hình XML truyền thống, cách khai báo phổ biến là:

~~~xml
<bean id="conversionService"
      class="org.springframework.context.support.ConversionServiceFactoryBean"/>
~~~

Có hai chi tiết rất quan trọng:

1. `ConversionServiceFactoryBean` là một **Spring FactoryBean**. Bean mà application context xuất ra dưới tên `conversionService` là sản phẩm `ConversionService` mà factory tạo ra.
2. Tên bean `conversionService` là **tên quy ước đặc biệt** mà Spring nhận diện để tìm conversion service dùng chung. Chỉ tạo bean tên tùy ý như `myConversions` không tự động tương đương với việc đăng ký conversion service mặc định của context.

Bài này giải thích vai trò factory bean, vì sao phải dùng tên `conversionService`, cách thêm custom converter, cách inject và sử dụng, cách tích hợp với MVC, cũng như những nhầm lẫn thường gặp. Ví dụ chính dùng Java 17+ và Spring Framework 6.2.

## 1. ConversionService là gì và được dùng ở đâu?

`ConversionService` nằm trong package `org.springframework.core.convert`. Đây là abstraction để hỏi và thực hiện chuyển đổi kiểu:

~~~java
boolean canConvert(Class<?> sourceType, Class<?> targetType);

<T> T convert(Object source, Class<T> targetType);
~~~

Ngoài hai overload trên, API còn hỗ trợ `TypeDescriptor` để mô tả generic type, annotation và metadata của field/property.

Ví dụ:

~~~java
Integer quantity = conversionService.convert("12", Integer.class);
LocalDate date = conversionService.convert("2026-11-02", LocalDate.class);
Priority priority = conversionService.convert("HIGH", Priority.class);
~~~

Các phép chuyển đổi cụ thể phụ thuộc những converter/formatter đã được đăng ký. Một conversion service thông thường hỗ trợ các nhóm chuyển đổi phổ biến như chuỗi, số, enum, collection, map và kiểu dữ liệu thông dụng khác.

Spring sử dụng conversion system trong nhiều tình huống, chẳng hạn:

- Bind giá trị property vào JavaBean qua `DataBinder`/`WebDataBinder`.
- Chuyển request parameter thành kiểu tham số trong Spring MVC.
- Thực hiện một số phép ép kiểu trong Spring Expression Language.
- Cho phép bean trong ứng dụng gọi `ConversionService.convert(...)` trực tiếp.

Ví dụ, một form gửi chuỗi `"12"` cho thuộc tính `Integer quantity`. Trong quá trình property binding, Spring cần tìm converter phù hợp để biến chuỗi thành số nguyên. Nếu không có conversion service được đăng ký theo cơ chế phù hợp, Spring vẫn có cơ chế chuyển đổi cũ dựa trên `PropertyEditor`; do đó không nên kết luận rằng ứng dụng không có bean `conversionService` thì mọi binding sẽ ngừng hoạt động.

## 2. ConversionServiceFactoryBean thực hiện điều gì?

`org.springframework.context.support.ConversionServiceFactoryBean` là một lớp triển khai `FactoryBean<ConversionService>`. Nó đóng vai trò tạo một conversion service đã được chuẩn bị cấu hình và đưa sản phẩm đó vào Spring container.

~~~text
ApplicationContext khởi động
           |
           v
 Tạo ConversionServiceFactoryBean
           |
           v
  Đọc các converter đã cấu hình
           |
           v
  Tạo ConversionService bên trong
           |
           v
 ApplicationContext cung cấp sản phẩm
    dưới bean name "conversionService"
           |
      +----+----------------+
      |                     |
      v                     v
 framework cần         bean ứng dụng inject
 type conversion       ConversionService
~~~

Phân biệt các thành phần:

| Tên/khái niệm | Vai trò |
| --- | --- |
| `ConversionService` | API mà code ứng dụng và Spring gọi để kiểm tra/thực hiện chuyển đổi. |
| `ConversionServiceFactoryBean` | Nhà máy Spring tạo một `ConversionService`. |
| `ConversionServiceFactory` | Utility factory trong Spring Core có thể tạo service theo cách lập trình; không phải cùng loại `FactoryBean` dùng khai báo bean XML. |
| `conversionService` | Bean name quy ước để Spring tìm conversion service trong application context. |
| `Converter<S,T>` / `ConverterFactory<S,R>` / `GenericConverter` | Các SPI triển khai logic chuyển đổi được đăng ký vào conversion service. |

Vì `ConversionServiceFactoryBean` là `FactoryBean`, phép tra cứu sau:

~~~java
ConversionService service =
        context.getBean("conversionService", ConversionService.class);
~~~

trả về **sản phẩm** mà factory cung cấp.

Muốn lấy đối tượng factory bean thay vì sản phẩm, dùng ký hiệu `&` trước tên bean:

~~~java
Object factory = context.getBean("&conversionService");
~~~

Thông thường code ứng dụng cần `ConversionService`, không cần thao tác trực tiếp với factory. Phép tra cứu `&conversionService` hữu ích khi tìm hiểu container, debug hoặc cần truy cập chính factory bean.

## 3. Vì sao bean phải có tên conversionService?

Spring quy định tên `conversionService` là tên đặc biệt để tự tìm conversion service của application context. Ví dụ XML:

~~~xml
<bean id="conversionService"
      class="org.springframework.context.support.ConversionServiceFactoryBean"/>
~~~

Sau khi context khởi động, khi một thành phần Spring cần conversion service mặc định, framework có thể tra cứu bean theo tên quy ước này.

Điều đó khác với dependency injection thông thường:

~~~xml
<bean id="myConversions"
      class="org.springframework.context.support.ConversionServiceFactoryBean"/>
~~~

Bean `myConversions` vẫn có thể được ứng dụng lấy và inject bằng tên hoặc kiểu (nếu không mơ hồ), nhưng **không nên giả định Spring tự coi nó là conversion service mặc định** chỉ vì kiểu sản phẩm là `ConversionService`. Khi cần framework nhận diện service chung, hãy dùng đúng tên quy ước hoặc đăng ký qua cơ chế cấu hình mà thành phần framework tương ứng yêu cầu.

### Có thể inject theo kiểu hay theo tên?

Khi chỉ có một bean sản phẩm kiểu `ConversionService`, constructor injection theo kiểu thường là rõ ràng:

~~~java
public PricingService(ConversionService conversionService) {
    this.conversionService = conversionService;
}
~~~

Nếu có nhiều bean cùng kiểu, cần xác định bean phù hợp bằng `@Qualifier` hoặc cấu hình `@Primary` theo contract ứng dụng. **Tên đặc biệt phục vụ tra cứu nội bộ của framework không tự giải quyết mọi trường hợp injection mơ hồ** trong application context.

## 4. Cấu hình cơ bản bằng XML

Ví dụ tối giản:

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="conversionService"
          class="org.springframework.context.support.ConversionServiceFactoryBean"/>

</beans>
~~~

Cấu hình này tạo conversion service với các converter mặc định mà Spring cung cấp. Ứng dụng có thể inject service vào bean khác:

~~~xml
<bean id="pricingService" class="example.PricingService">
    <constructor-arg ref="conversionService"/>
</bean>
~~~

Java:

~~~java
package example;

import org.springframework.core.convert.ConversionService;

public class PricingService {
    private final ConversionService conversionService;

    public PricingService(ConversionService conversionService) {
        this.conversionService = conversionService;
    }

    public Integer parseQuantity(String raw) {
        return conversionService.convert(raw, Integer.class);
    }
}
~~~

Đây là cách trực tiếp để một service nghiệp vụ sử dụng conversion service. Không cần gọi factory bean từ code nghiệp vụ; factory đã hoàn thành việc tạo sản phẩm khi container khởi tạo.

## 5. Đăng ký custom Converter qua thuộc tính converters

`ConversionServiceFactoryBean` cho phép bổ sung converter riêng thông qua property `converters`. Các phần tử trong collection có thể là implementation của:

- `Converter<S,T>`: một cặp kiểu nguồn/đích.
- `ConverterFactory<S,R>`: một kiểu nguồn chuyển sang nhiều kiểu đích cùng họ.
- `GenericConverter`: hỗ trợ nhiều cặp kiểu và có thể dùng `TypeDescriptor` để đọc metadata.

Ví dụ một custom converter chuyển `String` sang kiểu tiền tệ nội bộ:

~~~java
package example;

import java.math.BigDecimal;
import java.util.Currency;

public record Money(BigDecimal amount, Currency currency) {
}
~~~

~~~java
package example;

import java.math.BigDecimal;
import java.util.Currency;
import java.util.Locale;

import org.springframework.core.convert.converter.Converter;

public class StringToMoneyConverter implements Converter<String, Money> {

    @Override
    public Money convert(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException("Money input is required");
        }

        String[] parts = source.trim().split("\\\\s+");
        if (parts.length != 2) {
            throw new IllegalArgumentException(
                    "Expected amount and currency, for example: 125.50 USD");
        }

        BigDecimal amount = new BigDecimal(parts[0]);
        Currency currency =
                Currency.getInstance(parts[1].toUpperCase(Locale.ROOT));

        return new Money(amount, currency);
    }
}
~~~

Giả sử input là `"125.50 USD"`. Converter tách phần số và mã tiền tệ, tạo một record `Money`. Lỗi format hoặc mã tiền tệ không hợp lệ được báo bằng exception; conversion service sẽ thể hiện lỗi chuyển đổi theo cơ chế của nó.

XML đăng ký converter:

~~~xml
<bean id="conversionService"
      class="org.springframework.context.support.ConversionServiceFactoryBean">
    <property name="converters">
        <set>
            <bean class="example.StringToMoneyConverter"/>
        </set>
    </property>
</bean>
~~~

Spring khởi tạo bean converter được khai báo trong set và đưa vào conversion service. Từ đó code có thể gọi:

~~~java
Money money =
        conversionService.convert("125.50 USD", Money.class);
~~~

### Thay thế hay bổ sung converter mặc định?

Khai báo property `converters` dùng để **bổ sung custom converter vào service được factory tạo**; nó không có nghĩa các converter mặc định của Spring bị xóa hết. Converter riêng tham gia cùng registry, và việc converter nào được chọn còn phụ thuộc source/target type, metadata và các converter đã đăng ký.

Không nên đăng ký nhiều converter cạnh tranh cho cùng một cặp kiểu với kỳ vọng thứ tự trong XML luôn quyết định converter thắng. Nếu hai converter có cùng khả năng chuyển đổi, hãy thiết kế lại phạm vi hỗ trợ để tránh mơ hồ.

## 6. Chương trình Java 17+ chạy đầy đủ với ApplicationContext

Chương trình dưới đây trình bày cả ba điểm: bean tên `conversionService`, factory bean tạo sản phẩm và custom converter được đăng ký qua XML.

Cấu trúc dự án:

~~~text
conversion-service-factory-bean/
├── pom.xml
└── src
    └── main
        ├── java/example/Money.java
        ├── java/example/StringToMoneyConverter.java
        ├── java/example/PricingService.java
        ├── java/example/FactoryBeanDemo.java
        └── resources/conversion-context.xml
~~~

### 6.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>conversion-service-factory-bean</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>example.FactoryBeanDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. Money.java

~~~java
package example;

import java.math.BigDecimal;
import java.util.Currency;

public record Money(BigDecimal amount, Currency currency) {
}
~~~

### 6.3. StringToMoneyConverter.java

~~~java
package example;

import java.math.BigDecimal;
import java.util.Currency;
import java.util.Locale;

import org.springframework.core.convert.converter.Converter;

public class StringToMoneyConverter implements Converter<String, Money> {

    @Override
    public Money convert(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException("Money input is required");
        }

        String[] parts = source.trim().split("\\\\s+");
        if (parts.length != 2) {
            throw new IllegalArgumentException(
                    "Expected: amount currency, for example 125.50 USD");
        }

        BigDecimal amount = new BigDecimal(parts[0]);
        Currency currency =
                Currency.getInstance(parts[1].toUpperCase(Locale.ROOT));

        return new Money(amount, currency);
    }
}
~~~

### 6.4. PricingService.java

~~~java
package example;

import org.springframework.core.convert.ConversionService;

public class PricingService {
    private final ConversionService conversionService;

    public PricingService(ConversionService conversionService) {
        this.conversionService = conversionService;
    }

    public Money parse(String raw) {
        return conversionService.convert(raw, Money.class);
    }
}
~~~

### 6.5. conversion-context.xml

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="conversionService"
          class="org.springframework.context.support.ConversionServiceFactoryBean">
        <property name="converters">
            <set>
                <bean class="example.StringToMoneyConverter"/>
            </set>
        </property>
    </bean>

    <bean id="pricingService" class="example.PricingService">
        <constructor-arg ref="conversionService"/>
    </bean>

</beans>
~~~

### 6.6. FactoryBeanDemo.java

~~~java
package example;

import org.springframework.context.support.ClassPathXmlApplicationContext;
import org.springframework.core.convert.ConversionService;

public class FactoryBeanDemo {

    public static void main(String[] args) {
        try (var context = new ClassPathXmlApplicationContext(
                "conversion-context.xml")) {

            ConversionService service =
                    context.getBean("conversionService",
                            ConversionService.class);

            PricingService pricingService =
                    context.getBean(PricingService.class);

            Money direct =
                    service.convert("125.50 USD", Money.class);
            Money throughBean = pricingService.parse("20 EUR");

            Object factory =
                    context.getBean("&conversionService");

            System.out.println("isConversionService="
                    + (service instanceof ConversionService));
            System.out.println("direct="
                    + direct.amount().toPlainString() + " "
                    + direct.currency().getCurrencyCode());
            System.out.println("injected="
                    + throughBean.amount().toPlainString() + " "
                    + throughBean.currency().getCurrencyCode());
            System.out.println("factoryType="
                    + factory.getClass().getSimpleName());
        }
    }
}
~~~

### 6.7. Biên dịch và chạy

Từ thư mục gốc `conversion-service-factory-bean`, cần JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java
~~~

Kết quả stdout dự kiến:

~~~text
isConversionService=true
direct=125.50 USD
injected=20 EUR
factoryType=ConversionServiceFactoryBean
~~~

Giải thích:

1. `ClassPathXmlApplicationContext` đọc `conversion-context.xml` và tạo application context.
2. Bean định nghĩa bằng class `ConversionServiceFactoryBean` có tên `conversionService`. Khi tra cứu bean bằng kiểu `ConversionService`, ta nhận sản phẩm mà FactoryBean cung cấp.
3. `StringToMoneyConverter` được đưa vào set `converters`, rồi được đăng ký vào conversion service.
4. `PricingService` được inject cùng service qua constructor và gọi `convert(...)` giống như code nhận trực tiếp.
5. `context.getBean("&conversionService")` trả về chính factory bean; vì vậy tên kiểu in ra là `ConversionServiceFactoryBean`.

Mẫu output phụ thuộc vào các bước chuyển đổi của converter đã khai báo. Chương trình trên là một ví dụ nhỏ có class, XML và dependency đầy đủ; lệnh Maven sử dụng `exec-maven-plugin` để tự dựng classpath có Spring dependencies, không cần tự ghép thủ công classpath.

## 7. Tên bean conversionService trong Spring MVC

Spring MVC cũng cần conversion/formatting cho các request parameter và model attribute. Tuy nhiên, **conversion và formatting có phạm vi rộng hơn một tập converter thuần túy**: ngày tháng, số theo locale, annotation format và formatter hai chiều có thể tham gia.

Vì vậy tài liệu MVC sử dụng `FormattingConversionServiceFactoryBean` trong cấu hình XML cổ điển:

~~~xml
<mvc:annotation-driven conversion-service="conversionService"/>

<bean id="conversionService"
      class="org.springframework.format.support.FormattingConversionServiceFactoryBean">
    <property name="converters">
        <set>
            <bean class="example.StringToMoneyConverter"/>
        </set>
    </property>
</bean>
~~~

`FormattingConversionServiceFactoryBean` cũng tạo một conversion service, nhưng service có hỗ trợ hệ thống formatter/formatting của Spring. Khi cấu hình MVC bằng Java, cách hiện hành thường dùng `WebMvcConfigurer.addFormatters`:

~~~java
@Configuration
public class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToMoneyConverter());
    }
}
~~~

Không nhất thiết phải tự tạo cả hai cấu hình. Chọn đúng một cơ chế đăng ký cho từng application context và tránh nhiều registry trùng lặp không cần thiết.

| Nhu cầu | Lựa chọn |
| --- | --- |
| Conversion service dùng chung ở Spring Core, chủ yếu là Converter/ConverterFactory/GenericConverter | `ConversionServiceFactoryBean` |
| Cấu hình MVC cổ điển, cần converter và formatter | `FormattingConversionServiceFactoryBean` |
| MVC Java configuration | `WebMvcConfigurer.addFormatters(FormatterRegistry)` |
| Ứng dụng muốn gọi conversion trực tiếp trong code | Inject `ConversionService` |
| Chỉ cần chuyển đổi cho một điểm riêng | Cân nhắc binder/service riêng thay vì tạo registry toàn cục |

Tên `conversionService` là một convention có ích trong các cấu hình XML/Java container. Đối với MVC, cấu hình explicit qua `conversion-service="conversionService"` hoặc `addFormatters(...)` làm rõ registry được sử dụng. Đừng nhầm bean phục vụ property binding của core context với mọi conversion step của mọi HTTP message converter.

## 8. Spring Boot và Java configuration

Trong ứng dụng cấu hình Java thuần:

~~~java
@Configuration
public class CoreConversionConfiguration {

    @Bean
    public ConversionService conversionService() {
        DefaultConversionService service =
                new DefaultConversionService();
        service.addConverter(new StringToMoneyConverter());
        return service;
    }
}
~~~

Đây là cách khai báo trực tiếp một service qua `@Bean`; **không cần bọc bằng `ConversionServiceFactoryBean`** nếu bạn đã chủ động tạo instance. Tuy nhiên, cần phân biệt việc tạo bean thông thường với cách Spring framework hoặc MVC tìm registry theo tên/contract cụ thể.

Trong cấu hình web MVC:

~~~java
@Configuration
public class WebConversionConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToMoneyConverter());
    }
}
~~~

Cách này đăng ký converter vào registry mà MVC sử dụng. Với Spring Boot, hệ thống auto-configuration có thể quản lý application conversion service và web conversion service theo quy tắc riêng của Boot version. Nên ưu tiên extension point được tài liệu của đúng phiên bản Boot hướng dẫn, thay vì thêm một `ConversionServiceFactoryBean` thủ công bên cạnh cơ chế auto-configuration rồi tạo hai bộ conversion khác nhau.

Trước khi khai báo bean:

1. Kiểm tra ứng dụng đã có bean `ConversionService` hay chưa.
2. Xác định bean dành cho core/application context hay dành cho MVC.
3. Xác định có cần `Formatter`/locale hay chỉ converter thuần.
4. Chọn đúng một extension point và kiểm thử bean/service thực sự được framework sử dụng.

## 9. Vòng đời, thread safety và phạm vi application context

Spring mô tả `ConversionService` là đối tượng không giữ trạng thái thay đổi theo một lần chuyển đổi (stateless), được tạo khi ứng dụng khởi động và chia sẻ giữa nhiều thread. Vì vậy:

- Không tạo conversion service mới trên mỗi request.
- Converter không nên giữ state mutable riêng của từng người dùng.
- Không đưa thao tác ghi DB, gọi API hoặc kiểm tra quyền vào converter.
- Custom converter cần có hành vi ổn định khi được gọi đồng thời.
- Khi cần cấu hình theo request/locale, dùng cơ chế formatter hoặc truyền context phù hợp, không lưu locale hiện tại vào field mutable của singleton converter.

Một `ApplicationContext` thường có conversion service riêng. Trong ứng dụng có parent/child context, cần xác định context nào sở hữu bean `conversionService` mà thành phần đang dùng. Đừng cho rằng khai báo trong một context bất kỳ tự động cấu hình mọi child context; điều đó còn phụ thuộc cách khởi tạo và cấu hình web application.

### ConversionService có thay thế validation không?

Không. Converter giải quyết việc chuyển dữ liệu giữa hai kiểu:

~~~text
"12" -> Integer.valueOf(12)
~~~

Validation kiểm tra dữ liệu sau khi đã chuyển đổi:

~~~text
quantity = 12 -> quantity phải lớn hơn 0?
~~~

Business service kiểm tra điều kiện nghiệp vụ:

~~~text
quantity hợp lệ -> kho còn đủ hàng không?
~~~

Ba tầng có nhiệm vụ khác nhau. Một giá trị chuyển đổi thành công vẫn có thể không hợp lệ hoặc không được phép thực hiện nghiệp vụ. Ở luồng DataBinder, cần kiểm tra `BindingResult` và validation trước khi gọi service thay đổi trạng thái.

## 10. Các lỗi phổ biến khi cấu hình FactoryBean

**Lỗi 1 — Dùng tên bean tùy ý và mong Spring tự chọn.**

~~~xml
<bean id="myConversions"
      class="org.springframework.context.support.ConversionServiceFactoryBean"/>
~~~

Bean này vẫn có thể được inject, nhưng không tương đương với bean convention `conversionService`. Nếu cần đăng ký conversion service chung của context, dùng đúng tên quy ước hoặc extension point mà framework đang yêu cầu.

**Lỗi 2 — Nhầm factory bean với sản phẩm.**

~~~java
Object factory = context.getBean("conversionService");
~~~

Cách tra cứu thông thường lấy **sản phẩm**. Dùng `context.getBean("&conversionService")` mới lấy factory bean. Đừng inject `ConversionServiceFactoryBean` vào service chỉ để gọi chuyển đổi; service nên phụ thuộc `ConversionService`.

**Lỗi 3 — Nghĩ tên conversionService tự sinh mọi converter tùy chỉnh.**

Bean factory cung cấp tập converter mặc định của Spring và những converter mà bạn đăng ký qua property `converters`. Logic riêng như `StringToMoneyConverter` vẫn phải được viết và đăng ký.

**Lỗi 4 — Đăng ký converter không đúng generic type.**

Một converter `String -> Money` không thể tự xử lý `String -> Priority` trừ khi có một converter hoặc factory phù hợp khác. Định nghĩa chính xác kiểu nguồn và kiểu đích của từng converter.

**Lỗi 5 — Dùng ConversionServiceFactoryBean khi thực tế cần formatting.**

Nếu MVC phải parse/format ngày, số theo locale hoặc hỗ trợ `Formatter`, xem `FormattingConversionServiceFactoryBean` hoặc `WebMvcConfigurer.addFormatters`. Converter chỉ có một hướng chuyển đổi, còn Formatter thường mô tả cả parse và print.

**Lỗi 6 — Tạo hai conversion service không đồng bộ.**

Nếu core context có bean `conversionService` và MVC lại có registry khác, một converter có thể hoạt động khi gọi trực tiếp nhưng không được MVC sử dụng. Hãy kiểm thử đúng điểm tích hợp và tránh cấu hình trùng lặp.

**Lỗi 7 — Nghĩ canConvert bảo đảm convert sẽ thành công cho mọi giá trị.**

~~~java
conversionService.canConvert(String.class, Money.class)
~~~

Lệnh trên kiểm tra khả năng chuyển đổi theo kiểu. Nó không kiểm tra chuỗi cụ thể như `"abc"` có phải tiền tệ hợp lệ không. Chỉ `convert(...)` với giá trị thực mới chạy converter.

**Lỗi 8 — Ném exception không rõ nghĩa hoặc âm thầm trả null.**

Input không hợp lệ cần tạo lỗi chuyển đổi có thể quan sát. Không trả `null` như một cách che giấu dữ liệu sai khi contract không cho phép.

**Lỗi 9 — Quên dependency và classpath.**

`ConversionServiceFactoryBean` thuộc Spring Framework; một ứng dụng dùng XML context cần dependency phù hợp, thường thông qua `spring-context`. Khi chạy Java main có Spring dependencies, classpath phải có tất cả JAR liên quan; chỉ đưa `target/classes` sẽ không đủ.

**Lỗi 10 — Dùng chung API Core với Jackson.**

`ConversionService` không tự thay thế Jackson JSON deserializer. Một API `@RequestBody` thường đi qua HTTP message converter; một form `@ModelAttribute` dùng WebDataBinder/ConversionService. Kiểm thử đúng đường dữ liệu thực tế.

## 11. Cách kiểm thử cấu hình

Kiểm thử cấu hình nên xác minh ba lớp:

1. **Bean đúng tên và đúng sản phẩm:** `context.getBean("conversionService", ConversionService.class)` trả một conversion service.
2. **Custom converter được đăng ký:** giá trị mẫu thực sự chuyển sang kiểu đích mong muốn.
3. **Injection hoạt động:** bean ứng dụng nhận chính conversion service và gọi được.

Ví dụ JUnit 5 (đoạn trích, cần test dependency và XML context đã tạo):

~~~java
@Test
void customConverterIsAvailableFromNamedService() {
    try (var context = new ClassPathXmlApplicationContext(
            "conversion-context.xml")) {

        ConversionService service =
                context.getBean("conversionService",
                        ConversionService.class);

        Money money =
                service.convert("125.50 USD", Money.class);

        assertEquals(new BigDecimal("125.50"), money.amount());
        assertEquals("USD", money.currency().getCurrencyCode());
    }
}
~~~

Các ca test bổ sung hữu ích:

| Test | Điều cần xác minh |
| --- | --- |
| Bean name | Có bean `conversionService` và lấy được theo kiểu `ConversionService`. |
| Factory dereference | `&conversionService` trả factory bean, không phải sản phẩm. |
| Built-in conversion | String sang số/enum chuyển đúng theo service đã cấu hình. |
| Custom converter | String sang Money hoạt động. |
| Invalid input | Mã tiền tệ sai tạo lỗi conversion rõ ràng. |
| Injection | Service nghiệp vụ nhận ConversionService qua constructor. |
| MVC integration | Request form có kiểu đích cần chuyển đổi thực sự dùng registry MVC đã cấu hình. |
| Multiple contexts | Core/web context có service phù hợp và không tạo cấu hình trùng. |

Khi test lỗi, có thể assert `ConversionException` hoặc exception cụ thể theo đường gọi. Với `DataBinder`/MVC, conversion error thường được ghi thành `FieldError` để hiển thị lại cho người dùng, thay vì luôn truyền exception thẳng ra ngoài.

## 12. Quy trình triển khai

1. Xác định các điểm trong ứng dụng cần dùng chung chuyển đổi kiểu.
2. Chọn converter phù hợp: `Converter`, `ConverterFactory` hay `GenericConverter`.
3. Nếu dùng XML core context, khai báo `ConversionServiceFactoryBean` dưới bean name `conversionService`.
4. Đăng ký custom converter trong property `converters` của factory.
5. Inject sản phẩm dưới kiểu `ConversionService`, không phụ thuộc trực tiếp vào factory bean.
6. Nếu cấu hình Spring MVC và cần formatting, cân nhắc `FormattingConversionServiceFactoryBean` hoặc `WebMvcConfigurer.addFormatters`.
7. Khởi động context, kiểm tra bean name, converter được đăng ký và đường bind thực tế.
8. Đảm bảo converter stateless/thread-safe; xử lý lỗi conversion trước khi validation và nghiệp vụ tiếp tục.

**Hãy nhớ:** `ConversionServiceFactoryBean` là phương tiện cấu hình/tạo conversion service; `conversionService` là tên bean quy ước để Spring nhận diện service dùng chung; custom converter là những thành phần được thêm vào registry đó. Khi phân biệt rõ ba phần, việc cấu hình, inject và kiểm thử chuyển đổi kiểu sẽ dễ kiểm soát hơn.

### Tài liệu tham khảo Spring chính thức

- [Spring Framework — Spring Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework — ConversionServiceFactoryBean Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/support/ConversionServiceFactoryBean.html)
- [Spring Framework — ConversionService Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/ConversionService.html)
- [Spring Framework — ConverterRegistry Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/converter/ConverterRegistry.html)
- [Spring MVC — Type Conversion and FormatterRegistry](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html)
- [Spring Framework — FormattingConversionServiceFactoryBean Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/support/FormattingConversionServiceFactoryBean.html)
