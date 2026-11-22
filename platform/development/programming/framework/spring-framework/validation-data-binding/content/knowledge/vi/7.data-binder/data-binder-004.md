# Đặt ConversionService cho DataBinder trong Spring Framework

**DataBinder** chuyển dữ liệu bên ngoài (chẳng hạn chuỗi từ form hoặc các giá trị trong **PropertyValues**) sang thuộc tính của đối tượng Java. Khi một giá trị đầu vào và kiểu của property không giống nhau, binder cần cơ chế **type conversion**. Phương thức **DataBinder.setConversionService(ConversionService)** cho phép cung cấp một dịch vụ chuyển kiểu cho chính binder đó.

Ví dụ: client gửi **ticketCode = " vip-42 "**, trong khi đối tượng đích có thuộc tính **TicketCode ticketCode**. Ứng dụng có thể định nghĩa **Converter<String, TicketCode>** để chuẩn hóa mã thành **VIP-42** và dùng **ConversionService** chứa converter ấy khi binder gán property. Đây là chuyển đổi dữ liệu, chưa phải xác nhận mã vé có tồn tại hay người dùng có quyền sử dụng mã đó.

Bài này giải thích hợp đồng API, thứ tự cấu hình, cách thực hiện với **DataBinder** thuần, ảnh hưởng đến lỗi binding, và cách tích hợp đúng trong **Spring MVC**.

## 1. ConversionService là gì và DataBinder dùng nó như thế nào?

**org.springframework.core.convert.ConversionService** là hợp đồng yêu cầu chuyển đổi giá trị từ kiểu nguồn sang kiểu đích. Hai thao tác tiêu biểu là:

~~~java
boolean supported = conversionService.canConvert(String.class, TicketCode.class);
TicketCode converted = conversionService.convert(" vip-42 ", TicketCode.class);
~~~

Đây là đoạn minh họa với một converter **String → TicketCode** đã đăng ký; để chạy cần có biến **conversionService** và lớp **TicketCode** của ứng dụng.

Một **ConversionService** cơ bản cung cấp các khả năng **canConvert** và **convert**, còn việc **đăng ký** converter là trách nhiệm của các triển khai hỗ trợ **ConverterRegistry/ConfigurableConversionService**, chẳng hạn **DefaultConversionService** hoặc **DefaultFormattingConversionService**.

Các thành phần liên quan:

| Thành phần | Vai trò |
| --- | --- |
| **Converter<S,T>** | Chuyển một giá trị kiểu **S** sang kiểu **T**, phù hợp cho chuyển đổi không phụ thuộc locale. |
| **ConverterFactory<S,R>** | Cấp converter cho một họ kiểu đích, ví dụ họ enum. |
| **GenericConverter** | Xử lý những trường hợp phức tạp hơn cần biết **TypeDescriptor**, collection, generic hoặc nhiều cặp kiểu. |
| **ConversionService** | Tra cứu khả năng chuyển đổi rồi thực hiện chuyển đổi. |
| **FormattingConversionService** | Kết hợp **ConversionService** với **Formatter** để hỗ trợ parse/print theo locale, định dạng ngày/giờ và số. |
| **DataBinder** | Dùng dịch vụ chuyển kiểu được gắn để ánh xạ giá trị đầu vào sang property đích, lưu lỗi nếu không thể bind. |

Spring có sẵn nhiều phép chuyển đổi thông thường, ví dụ từ **String** sang số nguyên hoặc enum, nhưng không thể biết ý nghĩa của mọi kiểu nghiệp vụ tùy chỉnh. Vì vậy ta đăng ký converter và gắn dịch vụ chuyển đổi chứa nó vào binder.

Luồng điển hình:

~~~text
PropertyValues / request parameters
            |
            v
DataBinder.bind(...)
            |
            v
Tìm property và kiểu đích (ví dụ TicketCode, Integer)
            |
            v
ConversionService / cơ chế chuyển đổi thuộc tính
            |
            +-- Chuyển thành công --> gọi setter / gán giá trị
            |
            +-- Không chuyển được --> ghi lỗi typeMismatch vào BindingResult
            |
            v
DataBinder.getBindingResult() --> kiểm tra hasErrors() và FieldError
~~~

**Chuyển đổi thành công ≠ hợp lệ về nghiệp vụ.** String có thể đổi thành **TicketCode** đúng cấu trúc nhưng mã không còn hiệu lực. **ConversionService** giải quyết biểu diễn/kiểu dữ liệu; **Validator** hoặc service/domain giải quyết những ràng buộc cần kiểm tra tiếp. Cũng không nên đồng nhất ConversionService với **HttpMessageConverter**: với JSON body, Jackson thường deserialize JSON trước bước binding/validation liên quan đến controller, không phải mọi field JSON đều được đọc qua **DataBinder.bind(PropertyValues)**.

## 2. API DataBinder.setConversionService(...) và vòng đời cấu hình

Phương thức chính thuộc **org.springframework.validation.DataBinder**:

~~~java
void setConversionService(ConversionService conversionService);
ConversionService getConversionService();
~~~

**setConversionService(...)** xác định dịch vụ chuyển đổi dùng cho việc bind thuộc tính của binder. **getConversionService()** cho phép đọc dịch vụ đã gắn (có thể **null** nếu chưa cấu hình riêng).

Cách dùng chuẩn với một binder tự tạo:

~~~java
// order là một JavaBean do ứng dụng tạo.
// conversions là ConversionService đã có converter cần thiết.
DataBinder binder = new DataBinder(order, "order");
binder.setConversionService(conversions);     // cấu hình trước khi bind
binder.bind(new MutablePropertyValues(Map.of(
        "ticketCode", " vip-42 ",
        "quantity", "3"
)));
BindingResult result = binder.getBindingResult();
~~~

Đây là đoạn minh họa; ví dụ **chạy độc lập** ở phần 4 cung cấp đầy đủ class và imports.

Những điểm về thứ tự và phạm vi cần nắm:

1. Tạo **ConversionService** phù hợp; đăng ký **Converter** hoặc **Formatter** cần dùng lên triển khai hỗ trợ đăng ký.
2. Tạo **DataBinder** cho một target cụ thể.
3. Gọi **binder.setConversionService(conversions)** khi binder chưa được gắn dịch vụ khác. Trên các phiên bản Spring Framework hiện đại, gọi **setConversionService** lần nữa sau khi binder đã có dịch vụ chuyển đổi có thể gây **IllegalStateException** với thông báo binder đã được khởi tạo cùng ConversionService.
4. Gọi **bind(...)** để chuyển và gán dữ liệu; sau đó đọc **getBindingResult()**. Nếu muốn áp dụng validation đã đăng ký, gọi **validate(...)** riêng khi dùng DataBinder trực tiếp.
5. Việc đặt dịch vụ chuyển đổi trên một **DataBinder** chỉ tác động tới binder đó. Nó **không tự động** đổi dịch vụ chuyển kiểu của mọi controller, mọi bean, môi trường cấu hình hoặc toàn bộ ứng dụng.

Trong Spring MVC, framework thường đã cài một **FormattingConversionService** cho **WebDataBinder** thông qua cấu hình MVC chung. Vì vậy không nên tùy tiện gọi **setConversionService(new DefaultConversionService())** trong mọi **@InitBinder**: có thể xung đột với dịch vụ có sẵn, đồng thời làm mất những converter/formatter mà ứng dụng mong đợi. Khi mục tiêu là bổ sung converter cho mọi request MVC, chọn cách đăng ký ở **WebMvcConfigurer.addFormatters(...)** (phần 6).

## 3. Chọn triển khai và đăng ký Converter/Formatter

### 3.1. DefaultConversionService

**DefaultConversionService** trong **org.springframework.core.convert.support** tích hợp nhiều converter mặc định phù hợp cho chuyển đổi kiểu phổ thông. Nếu chỉ cần converter kiểu dữ liệu thông thường, có thể bắt đầu với:

~~~java
DefaultConversionService conversions = new DefaultConversionService();
conversions.addConverter(new StringToTicketCode());
~~~

Trong ví dụ này, **StringToTicketCode** là implementation do ứng dụng định nghĩa. **DefaultConversionService** vừa là **ConversionService** để sử dụng, vừa hỗ trợ đăng ký converter.

### 3.2. DefaultFormattingConversionService

**DefaultFormattingConversionService** trong **org.springframework.format.support** phù hợp khi có chuyển đổi gắn với biểu diễn UI, ngày giờ hoặc số được format theo locale. Nó cũng hỗ trợ **addConverter(...)**:

~~~java
DefaultFormattingConversionService conversions =
        new DefaultFormattingConversionService();
conversions.addConverter(new StringToTicketCode());
binder.setConversionService(conversions);
~~~

Dịch vụ này thường là điểm xuất phát thuận tiện trong ứng dụng web. Để đặt quy tắc hiển thị/nhập ngày chính xác, có thể thêm **Formatter** hoặc **DateTimeFormatterRegistrar**; không nên phụ thuộc mơ hồ vào định dạng mặc định của máy chủ hay locale.

### 3.3. Converter hay Formatter?

- Chọn **Converter<String, TicketCode>** khi giá trị có quy ước cú pháp ổn định không phụ thuộc ngôn ngữ, chẳng hạn mã định danh, SKU hoặc loại giá trị kỹ thuật.
- Chọn **Formatter<T>** khi cùng một giá trị có dạng chuỗi phụ thuộc **Locale**; nó có **parse(String, Locale)** và **print(T, Locale)**. Tiền tệ, ngày hiển thị và số theo vùng miền là ví dụ điển hình.
- Chọn **GenericConverter** khi cần logic dựa trên metadata kiểu đích/nguồn phức tạp hơn.
- Với kiểu phổ biến như **Integer**, **Boolean**, enum, trước tiên kiểm tra converter mặc định; tránh đăng ký lại không cần thiết.

**Không thay thế toàn bộ ConversionService của ứng dụng chỉ vì muốn xử lý một field.** Tùy phạm vi, đăng ký converter cho MVC hoặc thêm một formatter riêng vào binder sẽ dễ bảo trì hơn.

## 4. Ví dụ hoàn chỉnh Java 17: gắn ConversionService và bind dữ liệu

Ví dụ Maven tối thiểu chạy mà **không cần khởi động Spring Boot hoặc web server**. Nó tạo một JavaBean **OrderForm**, gắn **DefaultFormattingConversionService** đã có **Converter<String, TicketCode>**, bind dữ liệu chuỗi rồi kiểm tra hai trường hợp thành công/thất bại.

Cấu trúc file:

~~~text
binder-conversion-example/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BinderConversionDemo.java
~~~

**pom.xml** — Spring Framework 6.2.10, Java 17:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>binder-conversion-example</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.10</version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/BinderConversionDemo.java**:

~~~java
package demo;

import java.util.Locale;
import java.util.Map;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.core.convert.converter.Converter;
import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

public final class BinderConversionDemo {

    public static void main(String[] args) {
        // 1. Đăng ký converter lên một service có sẵn converter mặc định.
        DefaultFormattingConversionService conversions =
                new DefaultFormattingConversionService();
        conversions.addConverter(new StringToTicketCode());

        // 2. Tạo binder mới, đặt ConversionService trước khi bind.
        OrderForm order = new OrderForm();
        DataBinder binder = new DataBinder(order, "order");
        binder.setConversionService(conversions);

        // 3. Mọi giá trị từ form trong ví dụ là String.
        binder.bind(new MutablePropertyValues(Map.of(
                "ticketCode", " vip-42 ",
                "quantity", "3"
        )));

        BindingResult result = binder.getBindingResult();

        System.out.println("configured = "
                + (binder.getConversionService() == conversions));
        System.out.println("hasErrors = " + result.hasErrors());
        System.out.println("ticketCode = " + order.getTicketCode().getValue());
        System.out.println("quantity = " + order.getQuantity());

        // 4. Dữ liệu không thể đổi sang Integer: binder thu lỗi typeMismatch.
        OrderForm bad = new OrderForm();
        DataBinder badBinder = new DataBinder(bad, "order");
        badBinder.setConversionService(conversions);
        badBinder.bind(new MutablePropertyValues(Map.of(
                "ticketCode", "regular-7",
                "quantity", "wrong"
        )));

        BindingResult badResult = badBinder.getBindingResult();
        boolean quantityBindingFailure = badResult.getFieldErrors("quantity")
                .stream()
                .anyMatch(FieldError::isBindingFailure);

        System.out.println("bad.hasErrors = " + badResult.hasErrors());
        System.out.println("bad.quantityBindingFailure = "
                + quantityBindingFailure);
        System.out.println("bad.quantity = " + bad.getQuantity());
    }

    // Kiểu nghiệp vụ tùy chỉnh, không phải String hay Integer.
    public static final class TicketCode {
        private final String value;

        private TicketCode(String value) {
            this.value = value;
        }

        public String getValue() {
            return value;
        }

        public static TicketCode parse(String source) {
            String normalized = source.trim().toUpperCase(Locale.ROOT);
            if (normalized.isBlank()) {
                throw new IllegalArgumentException("Ticket code is blank");
            }
            return new TicketCode(normalized);
        }
    }

    public static final class StringToTicketCode
            implements Converter<String, TicketCode> {

        @Override
        public TicketCode convert(String source) {
            return TicketCode.parse(source);
        }
    }

    // JavaBean cho property binding: cần getter/setter công khai.
    public static final class OrderForm {
        private TicketCode ticketCode;
        private Integer quantity;

        public TicketCode getTicketCode() {
            return ticketCode;
        }

        public void setTicketCode(TicketCode ticketCode) {
            this.ticketCode = ticketCode;
        }

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }
    }
}
~~~

Từ thư mục chứa **pom.xml**, dùng JDK 17+ và Maven để chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.BinderConversionDemo
~~~

**Các dòng do chương trình in ra, theo thứ tự:**

~~~text
configured = true
hasErrors = false
ticketCode = VIP-42
quantity = 3
bad.hasErrors = true
bad.quantityBindingFailure = true
bad.quantity = null
~~~

Giải thích chi tiết:

- Giá trị **" vip-42 "** được **StringToTicketCode.convert(...)** chuẩn hóa thành **VIP-42**; setter nhận đối tượng **TicketCode**, không phải chuỗi.
- Giá trị **"3"** được converter mặc định chuyển sang **Integer 3**. Nếu tự tạo một **GenericConversionService** trống mà không đăng ký các converter mặc định, thao tác phổ biến này có thể thiếu hỗ trợ.
- **binder.getConversionService() == conversions** đúng vì binder giữ tham chiếu đến đối tượng đã đặt.
- Trường **quantity = "wrong"** không đổi được thành **Integer**. **DataBinder.bind(...)** thường ghi lỗi chuyển kiểu vào **BindingResult**, và **FieldError.isBindingFailure()** cho biết đó là lỗi binding. Property **quantity** của object **bad** còn **null** vì phép gán không thành công.
- **DataBinder** trực tiếp không tự chạy một business validator sau lời gọi **bind(...)**. Đoạn mã chỉ xác minh chuyển kiểu và trạng thái binding; nó chưa kiểm tra tồn kho, quyền sở hữu hoặc các constraint do ứng dụng khai báo.

**Quan trọng:** converter ở đây chỉ parse/chuẩn hóa cú pháp. Nếu một mã vé nhìn đúng kiểu nhưng không tồn tại, việc tra database và quyết định có cho phép đặt vé hay không thuộc tầng service/domain, không được coi là kết quả bắt buộc của **setConversionService(...)**.

### Tại sao cần hai binder?

Mỗi **DataBinder** gắn với một target cụ thể và giữ trạng thái **BindingResult** riêng. Dùng binder mới cho ví dụ lỗi giúp không trộn kết quả của hai lượt bind. Cả hai binder có thể dùng chung một **ConversionService** đã cấu hình trước. Với service dùng chung trong môi trường nhiều luồng, nên hoàn tất đăng ký converters/formatters trong giai đoạn khởi tạo, tránh thay đổi registry tùy tiện lúc nhiều request đang xử lý.

## 5. Xử lý lỗi khi converter thất bại

Một **Converter** có thể ném **IllegalArgumentException** hoặc một ngoại lệ phù hợp khi nguồn không có định dạng mong đợi. Với data binding vào property, Spring có thể chuyển lỗi đó thành **typeMismatch** trong **BindingResult**. Trong một ngữ cảnh khác, chẳng hạn gọi trực tiếp **conversionService.convert(...)**, lỗi có thể xuất hiện dưới dạng ngoại lệ chuyển đổi (ví dụ **ConversionFailedException**) để bên gọi xử lý.

| Tình huống | Tầng nhận biết | Cách xử lý |
| --- | --- | --- |
| **"3" → Integer** | ConversionService có converter thích hợp | Gán **3** vào property |
| **"wrong" → Integer** | Không parse được số | DataBinder lưu **FieldError**, thường có code **typeMismatch** |
| Chuỗi rỗng cho TicketCode do custom converter cấm | **StringToTicketCode** phát hiện cú pháp sai | Converter báo lỗi; binder có thể ghi **typeMismatch** |
| TicketCode đúng cú pháp nhưng mã đã hết hiệu lực | Không phải lỗi parse kiểu | Validator/service/domain từ chối theo quy tắc thực tế |
| JSON body sai cú pháp | **HttpMessageConverter/Jackson** | Có thể bị từ chối trước khi handler/controller chạy; không mặc nhiên nằm trong BindingResult của property binding |

Cần kiểm tra **BindingResult.hasErrors()**, **getFieldErrors()**, **getFieldError("ticketCode")**, mã lỗi và **isBindingFailure()** để hiển thị thông báo chính xác. Hãy phân biệt lỗi chuyển kiểu với lỗi validation của **@NotNull**, **@Min** hay business rule: những lỗi ấy có thể cùng được thể hiện qua **BindingResult/Errors** sau các bước tương ứng, nhưng nguyên nhân và cách khắc phục khác nhau.

**Không dùng ConversionService để nuốt lỗi** bằng cách trả về giá trị mặc định “có vẻ hợp lệ” khi chuỗi sai (ví dụ biến mọi số không parse được thành 0). Cách làm đó có thể khiến dữ liệu không hợp lệ bị ghi vào domain model. Hãy để lỗi được phát hiện rõ ràng và biểu diễn thành thông tin đầu vào sai.

## 6. Spring MVC: Đặt một lần trong hệ thống hay cấu hình cho từng binder?

### 6.1. Đăng ký dùng chung với WebMvcConfigurer.addFormatters(...)

Trong Spring MVC, **FormattingConversionService** thường đã được cấu hình bởi framework. Nếu muốn mọi request form/parameter có thể đổi **String** sang **TicketCode**, hãy bổ sung converter vào registry MVC:

~~~java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcBindingConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new BinderConversionDemo.StringToTicketCode());
    }
}
~~~

Đây là **ví dụ cấu hình trong dự án có Spring MVC** và dùng lại class converter từ phần 4. Để biên dịch riêng file này phải có dependency **spring-webmvc**, đồng thời đặt file trong package **demo** với tên **MvcBindingConfig.java**; nó không cần thêm vào chương trình Maven console đã minh họa.

**addFormatters** được Spring MVC gọi khi khởi tạo registry, nên converter được thêm vào dịch vụ chuyển đổi dùng chung. Đây là cách thường phù hợp hơn việc tạo ConversionService mới trong mọi controller. Với **Spring Boot**, viết một **WebMvcConfigurer** thông thường thường đủ để bổ sung converter; không tự thêm **@EnableWebMvc** chỉ để đăng ký một converter vì điều đó thay đổi cách Spring Boot quản lý cấu hình MVC.

Một ứng dụng có thể có các ConversionService **khác nhau**: MVC cho các request/format UI, binding cấu hình ứng dụng (**application.properties/application.yml**) và các dịch vụ được tự tạo. Đăng ký ở **WebMvcConfigurer** không có nghĩa converter tự xuất hiện ở mọi ConversionService khác; xác định đúng phạm vi bạn muốn cấu hình.

### 6.2. @InitBinder cho phạm vi controller/thuộc tính

**@InitBinder** dùng để tùy chỉnh **WebDataBinder** cho controller hiện tại (hoặc theo tên model attribute). Ví dụ, nếu một form chứa thuộc tính kiểu **java.util.Date** cần parse một định dạng riêng:

~~~java
// Đoạn minh họa bên trong @Controller có sẵn.
@InitBinder("order")
void initBinder(WebDataBinder binder) {
    binder.addCustomFormatter(new DateFormatter("yyyy-MM-dd"));
}
~~~

Đoạn này sử dụng **org.springframework.format.datetime.DateFormatter** để hỗ trợ **java.util.Date**, không phải **java.time.LocalDate**; import **WebDataBinder** và **InitBinder** từ Spring. **addCustomFormatter(...)** đăng ký formatter cục bộ với binder. Một lựa chọn khác là **registerCustomEditor(...)** cho PropertyEditor kiểu cũ, nhưng converter/formatter thường dễ dùng chung hơn.

**Lưu ý:** đừng gọi **binder.setConversionService(...)** trong **@InitBinder** nếu binder đã được MVC initializer gắn ConversionService; việc đặt lần hai có thể bị từ chối. Muốn thay dịch vụ của toàn bộ binder MVC phải cấu hình đúng tầng **WebBindingInitializer/MVC infrastructure** với hiểu biết về các converter/formatter được tích hợp sẵn; với bài toán đơn giản, **addFormatters** hoặc **addCustomFormatter** là giải pháp đúng phạm vi hơn.

### 6.3. Binding và message conversion không phải một

- **@ModelAttribute / form parameters:** Spring tạo hoặc lấy object, ánh xạ tham số sang các property, có thể nhờ **WebDataBinder** và ConversionService.
- **@RequestParam / @PathVariable:** Spring cũng dùng cơ chế type conversion cho tham số/giá trị từ URL theo cấu hình MVC thích hợp.
- **@RequestBody JSON:** converter đọc HTTP body (ví dụ Jackson) chịu trách nhiệm deserialize JSON; một **Converter<String, TicketCode>** trong ConversionService của WebDataBinder không có nghĩa Jackson tự động gọi nó cho mọi thuộc tính JSON. Nếu muốn điều khiển JSON format, xem Jackson module/deserializer/creator phù hợp.

Phải xác định **dữ liệu đi vào bằng đường nào** trước khi kết luận một converter vừa đăng ký sẽ được gọi.

## 7. Những ranh giới mà ConversionService không giải quyết

**Không thay thế Validator:** Set ConversionService chỉ thiết lập khả năng chuyển kiểu. Đối tượng có thể là **quantity = -4** (kiểu Integer hợp lệ) nhưng vi phạm **@Min(1)**. Để kiểm tra constraint, cần bước validation được kích hoạt, chẳng hạn **@Valid** trong MVC với provider phù hợp hoặc **binder.validate(...)** sau khi đã đăng ký validator.

**Không quyết định quyền và quy tắc nghiệp vụ:** Mã khách hàng được parse thành kiểu **CustomerId** chưa chứng minh người dùng sở hữu khách hàng đó. Các quy tắc bảo mật, tồn kho, hạn mức, trạng thái và ràng buộc dữ liệu vẫn thuộc service/domain và cơ sở dữ liệu.

**Không tạo field mới hoặc tự cho phép mọi field:** Binding có thể bị giới hạn bởi **allowedFields**, constructor binding và thiết kế request DTO. Chuyển kiểu có thể thực hiện thành công cho một field nhưng field đó vẫn bị loại khỏi quá trình bind do cấu hình an toàn.

**Không thay thế MessageSource:** Formatter parse/print theo locale khác với việc dịch thông báo lỗi dựa trên mã lỗi và locale của người dùng.

**Không tự bảo đảm round-trip format:** Converter một chiều **String → TicketCode** không mặc nhiên cung cấp logic in ngược **TicketCode → String** theo mong muốn. Nếu UI cần hai chiều, đăng ký chiều ngược hoặc viết **Formatter<TicketCode>** có **parse/print** thích hợp.

## 8. Lỗi triển khai phổ biến và cách tránh

**Gọi setConversionService lần hai trên binder đã được MVC cấu hình.** Kiểm tra bối cảnh khởi tạo và **getConversionService()**; thêm converter vào MVC registry thay vì thay cả service tùy tiện.

**Dùng GenericConversionService rỗng mà mong String → Integer luôn có sẵn.** Bắt đầu từ **DefaultConversionService/DefaultFormattingConversionService** nếu muốn có bộ converter phổ biến, hoặc chủ động đăng ký đủ chuyển đổi cần thiết.

**Viết Converter có side effect hoặc truy vấn DB cho mỗi keystroke.** Binding/formatting có thể diễn ra ở nhiều ngữ cảnh. Giữ converter thuần túy, nhanh và dễ dự đoán; để business validation ở tầng xử lý phù hợp.

**Ném lỗi rồi bắt và bỏ qua mọi exception ở controller.** Với data binding, đọc **BindingResult**, phân biệt **typeMismatch** với constraint validation. Không tiếp tục lưu đối tượng khi một field quan trọng không bind được.

**Nhầm Converter và Formatter khi dữ liệu phụ thuộc locale.** Chuyển số hoặc ngày dùng trên UI cần xét locale/format rõ ràng. Với form HTML date/time, chọn cách parse theo định dạng trình duyệt thay vì phụ thuộc locale của server.

**Đăng ký converter cho sai hướng.** **Converter<String, TicketCode>** chỉ nói về đầu vào String sang TicketCode; nó không cung cấp tính đối xứng cho kiểu ngược.

**Sửa chung registry lúc request đang chạy.** Cấu hình converter/formatter lúc khởi tạo ứng dụng; nếu nhiều request dùng chung service, tránh thay đổi cấu hình động thiếu kiểm soát.

**Cho bind trực tiếp entity với mọi setter.** Converter không ngăn mass assignment. Sử dụng request DTO riêng, constructor binding hoặc **allowedFields** khi cần; không cho client đặt các property như **role**, **ownerId** hoặc trạng thái mà server phải quản lý.

## 9. Chiến lược kiểm thử

Nên kiểm tra các tầng độc lập thay vì chỉ thử một request happy path:

| Trường hợp | Dữ liệu hoặc cấu hình | Kỳ vọng |
| --- | --- | --- |
| Converter có đăng ký | **String → TicketCode** | **canConvert(...) == true** |
| Bind thành công | **" vip-42 "** và **"3"** | **TicketCode VIP-42**, **quantity 3**, không có lỗi binding |
| Chuyển kiểu thất bại | **quantity = "wrong"** | **BindingResult.hasErrors() == true**, FieldError **quantity** là binding failure |
| Mã không đúng cú pháp | Chuỗi trắng cho TicketCode | Converter báo lỗi và được thể hiện đúng tại ranh giới gọi/bind |
| Thiếu converter chuyên biệt | Binder không có hỗ trợ String → custom type | Có lỗi chuyển kiểu hoặc bị từ chối; không đoán rằng Spring tự suy ra cú pháp domain |
| Chỉ có converter, chưa validate | **quantity = -1** | Có thể bind thành Integer -1; validation phải được kích hoạt riêng |
| Phạm vi MVC | Converter được đăng ký qua **addFormatters** | Các endpoint dùng conversion service MVC phù hợp nhận được converter |
| JSON body | Gửi JSON chứa TicketCode | Kiểm tra deserializer Jackson độc lập với property binder |
| Quyền/Business rule | TicketCode đúng kiểu nhưng không hợp lệ theo trạng thái hiện tại | Tầng domain/service từ chối, không lẫn với lỗi conversion |

Với test dùng **DataBinder** trực tiếp, hãy khẳng định cả giá trị object lẫn **BindingResult**. Với **MockMvc**, kiểm tra một endpoint dùng **@ModelAttribute** hoặc **@RequestParam** để xác nhận converter đã xuất hiện đúng phạm vi, và đừng dùng test JSON để kết luận chắc chắn đường property binding chạy.

## 10. Ghi nhớ khi áp dụng

Để đặt **ConversionService** cho **DataBinder** tự tạo, bạn cần **một service đã đăng ký converter**, rồi gọi **setConversionService(...)** trên **binder trước khi bind**, và kiểm tra **BindingResult** sau khi bind. Với **Spring MVC**, ưu tiên cấu hình converter/formatter trong **WebMvcConfigurer.addFormatters(...)**, giữ nguyên dịch vụ chuyển đổi mà framework đã tạo. Mọi logic kiểm tra ràng buộc và nghiệp vụ phải tiếp tục diễn ra sau hoặc song song với bước chuyển kiểu, tùy luồng xử lý đã thiết kế.

## Tài liệu chính thức

- [Spring Framework API — DataBinder.setConversionService / getConversionService](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework — Spring Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html)
- [Spring MVC — Type Conversion / addFormatters](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html)
- [Spring MVC — @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
