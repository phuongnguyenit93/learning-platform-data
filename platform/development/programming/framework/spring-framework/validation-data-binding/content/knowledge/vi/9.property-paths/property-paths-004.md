# Chuyển kiểu phần tử dựa trên thông tin generic trong Spring Data Binding

Khi request gửi chuỗi `"7"` để điền vào phần tử của `List<Integer>`, Spring cần biết **kiểu của từng phần tử** là `Integer`, thay vì chỉ biết toàn bộ thuộc tính là `List`. Tương tự, với `Map<String, BigDecimal>`, Spring cần phân biệt kiểu khóa `String` và kiểu giá trị `BigDecimal` để chuyển đầu vào `"19.50"` thành một số thập phân thực sự.

Spring Framework dùng thông tin kiểu khai báo của JavaBean property (bao gồm generic type), cơ chế truy cập property path và `ConversionService` để thực hiện việc chuyển kiểu. Chủ đề quan trọng là: **đường dẫn xác định phần tử đích; metadata generic xác định kiểu cần chuyển; bộ chuyển đổi thực hiện phép chuyển; `BindingResult` ghi nhận lỗi nếu chuyển không thành công**.

## 1. Đọc đúng kiểu phần tử: `List<Integer>` khác `List<String>`

Xét JavaBean:

~~~java
public class OrderForm {
    private List<Integer> quantities = new ArrayList<>();
    private Map<String, BigDecimal> prices = new LinkedHashMap<>();

    public List<Integer> getQuantities() {
        return quantities;
    }

    public void setQuantities(List<Integer> quantities) {
        this.quantities = quantities;
    }

    public Map<String, BigDecimal> getPrices() {
        return prices;
    }

    public void setPrices(Map<String, BigDecimal> prices) {
        this.prices = prices;
    }
}
~~~

Ví dụ trên là phần khai báo minh họa, cần imports `java.util.List`, `ArrayList`, `Map`, `LinkedHashMap` và `java.math.BigDecimal` khi sử dụng trong ứng dụng.

- `quantities` có **kiểu container** là `List` và **kiểu element** là `Integer`.
- `prices` có **kiểu container** là `Map`, **kiểu key** là `String`, **kiểu value** là `BigDecimal`.
- Giá trị từ form và query string thường đến dưới dạng chuỗi. Nếu binding thành công, `quantities.get(0)` phải là `Integer`, còn `prices.get("book")` phải là `BigDecimal`.
- Generic `<Integer>` và `<String, BigDecimal>` là **metadata về kiểu được khai báo**, không phải ký tự nằm trong tên field gửi từ client.

Java có **type erasure**, nghĩa là chỉ gọi `someList.getClass()` không đủ để biết chắc tham số kiểu `Integer`. Tuy vậy, metadata generic của **field, getter, setter hoặc tham số có khai báo kiểu** vẫn có thể được phản chiếu. Spring sử dụng ngữ cảnh JavaBean/property này để phân giải kiểu của phần tử. Nếu chỉ đưa một `List` dạng raw type mà không cung cấp đích có metadata, Spring có thể không xác định được kiểu element mong muốn.

## 2. Property path cho biết chính xác phần tử nào cần bind

Ký pháp property path của `BeanWrapper`/`DataBinder` kết hợp tên property với dấu chấm, chỉ số và khóa map:

| Đường dẫn | Đích được trỏ đến | Kiểu đích dự kiến |
| --- | --- | --- |
| `quantities` | Toàn bộ danh sách `List<Integer>` | `List<Integer>` |
| `quantities[0]` | Phần tử đầu tiên của `quantities` | `Integer` |
| `quantities[1]` | Phần tử thứ hai | `Integer` |
| `prices[book]` | Giá trị ứng với khóa `"book"` của `prices` | `BigDecimal` |
| `lines[0].quantity` | Property `quantity` của phần tử đầu tiên trong `List<OrderLine>` | Kiểu `quantity` được khai báo, ví dụ `Integer` |
| `limits[42]` | Entry của map có key `42` | Kiểu key và value dựa vào generic của `Map<K,V>` |

Đường dẫn `quantities[1]` sử dụng **chỉ số zero-based**, vì vậy `[1]` là phần tử thứ hai. Đối với map, phần trong `[...]` được hiểu là key. Ví dụ `prices[book]` trỏ đến key `book`, không phải thuộc tính JavaBean tên `book`.

Spring phải giải quyết hai việc tách biệt: tìm phần tử đích qua property path, sau đó chuyển giá trị nguồn sang **kiểu element/value** đã phân giải. Ví dụ:

~~~text
property path: quantities[1]
source value : "12" (String)
container    : List<Integer>
element type : Integer
conversion   : String -> Integer
result       : quantities.get(1) == Integer.valueOf(12)
~~~

Với `lines[0].quantity`, binder truy cập phần tử thứ nhất rồi property `quantity` bên trong nó. Muốn ghi thành công, đối tượng và cấu trúc chứa cần có khả năng truy cập hoặc được tạo thêm theo cấu hình. `DataBinder` có khả năng tự mở rộng một số nested path/collection khi được bật, nhưng việc này có giới hạn và không nên coi là cơ chế tạo bất kỳ đồ thị đối tượng nào không giới hạn.

## 3. Cơ chế phân giải generic: từ JavaBean đến `TypeDescriptor`

Luồng xử lý ở mức khái niệm:

~~~text
JavaBean:
  List<Integer> quantities
  Map<String, BigDecimal> prices
            |
            v
Reflection / ResolvableType / property metadata
            |
            v
BeanWrapper + property path
  quantities[1] -> Integer
  prices[book]  -> BigDecimal
            |
            v
TypeDescriptor (kiểu đích và ngữ cảnh generic)
            |
            v
ConversionService / converters
  "12"    -> Integer(12)
  "19.50" -> BigDecimal("19.50")
            |
            v
Gán vào list / map của JavaBean
  hoặc đưa lỗi chuyển kiểu vào BindingResult
~~~

Các khái niệm có vai trò khác nhau:

- `BeanWrapper` / `BeanWrapperImpl` hiểu **JavaBean property** và các đường dẫn lồng nhau, indexed và mapped; `DataBinder` sử dụng cơ chế property access đó khi thực hiện property binding.
- `ResolvableType` là abstraction để biểu diễn và truy vấn metadata kiểu Java, gồm cả tham số generic.
- `TypeDescriptor` biểu diễn kiểu đích có ngữ cảnh, ví dụ `List<Integer>` gồm kiểu collection và kiểu element; với map còn có key/value type. API hữu ích là `getElementTypeDescriptor()`, `getMapKeyTypeDescriptor()` và `getMapValueTypeDescriptor()`.
- `ConversionService` chọn converter phù hợp theo kiểu nguồn và kiểu đích. `DefaultConversionService` cung cấp sẵn nhiều phép chuyển đổi giữa chuỗi, số, enum, collection và map.
- `GenericConverter` nhận cả `sourceType` và `targetType` là `TypeDescriptor`; nhờ vậy converter ở cấp container có thể chuyển **từng phần tử** theo metadata thay vì chỉ xem container là `List.class`.

**Không nhầm generic metadata với runtime validation.** Thông tin `List<Integer>` cho phép chuyển `"12"` thành `Integer`, nhưng không khẳng định số 12 là hợp lệ về nghiệp vụ. Giới hạn min/max, số lượng phần tử hay quy tắc trùng lặp phải được kiểm tra bởi validation riêng.

## 4. Ví dụ Java 17+ chạy được: bind `List<Integer>` và `Map<String, BigDecimal>`

Ví dụ dưới đây sử dụng **Spring Framework 6.2.x**, không cần HTTP server. Nó khởi tạo list có sẵn hai phần tử để tập trung vào **chuyển kiểu** thay vì khả năng tự mở rộng collection. Mã hoàn chỉnh đặt tại `src/main/java/GenericElementBindingDemo.java` trong một dự án Maven sử dụng `spring-context`.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

public final class GenericElementBindingDemo {

    public static class OrderForm {
        private List<Integer> quantities =
                new ArrayList<>(List.of(0, 0));

        private Map<String, BigDecimal> prices =
                new LinkedHashMap<>();

        public List<Integer> getQuantities() {
            return quantities;
        }

        public void setQuantities(List<Integer> quantities) {
            this.quantities = quantities;
        }

        public Map<String, BigDecimal> getPrices() {
            return prices;
        }

        public void setPrices(Map<String, BigDecimal> prices) {
            this.prices = prices;
        }
    }

    public static void main(String[] args) {
        OrderForm form = new OrderForm();

        // Đọc metadata của JavaBean trước khi bind.
        BeanWrapper wrapper = new BeanWrapperImpl(form);
        TypeDescriptor quantityDescriptor =
                wrapper.getPropertyTypeDescriptor("quantities");
        TypeDescriptor priceDescriptor =
                wrapper.getPropertyTypeDescriptor("prices");

        System.out.println("elementType="
                + quantityDescriptor.getElementTypeDescriptor()
                        .getType().getSimpleName());
        System.out.println("mapValueType="
                + priceDescriptor.getMapValueTypeDescriptor()
                        .getType().getSimpleName());

        DataBinder binder = new DataBinder(form, "orderForm");
        binder.setConversionService(new DefaultConversionService());

        // Chỉ chấp nhận các field được demo chủ động cho phép.
        binder.setAllowedFields(
                "quantities[0]", "quantities[1]", "prices[book]");

        MutablePropertyValues input = new MutablePropertyValues();
        input.add("quantities[0]", "7");
        input.add("quantities[1]", "12");
        input.add("prices[book]", "19.50");

        binder.bind(input);

        BindingResult result = binder.getBindingResult();
        System.out.println("errors=" + result.getErrorCount());
        System.out.println("quantities=" + form.getQuantities());
        System.out.println("price=" + form.getPrices().get("book"));
        System.out.println("firstRuntimeType="
                + form.getQuantities().get(0).getClass().getSimpleName());
        System.out.println("priceRuntimeType="
                + form.getPrices().get("book").getClass().getSimpleName());

        // Một giá trị không thể chuyển sang Integer.
        DataBinder invalidBinder =
                new DataBinder(new OrderForm(), "orderForm");
        invalidBinder.setConversionService(new DefaultConversionService());
        invalidBinder.setAllowedFields("quantities[0]");

        MutablePropertyValues invalid = new MutablePropertyValues();
        invalid.add("quantities[0]", "not-a-number");
        invalidBinder.bind(invalid);

        FieldError fieldError = invalidBinder.getBindingResult()
                .getFieldError("quantities[0]");
        System.out.println("invalidHasError="
                + (fieldError != null));
        System.out.println("invalidBindingFailure="
                + (fieldError != null && fieldError.isBindingFailure()));
    }
}
~~~

Đối với Spring Framework 6.2.x (với converter mặc định), kết quả stdout mong đợi:

~~~text
elementType=Integer
mapValueType=BigDecimal
errors=0
quantities=[7, 12]
price=19.50
firstRuntimeType=Integer
priceRuntimeType=BigDecimal
invalidHasError=true
invalidBindingFailure=true
~~~

Để chạy bằng Maven, dùng Java 17+ và khai báo dependency tương thích trong `pom.xml` (ví dụ Spring 6.2.x). Một cấu hình minh họa tối thiểu:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>generic-element-binding-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Sau khi tạo đúng file Java và `pom.xml`, chạy từ thư mục project:

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=GenericElementBindingDemo
~~~

Lệnh yêu cầu Maven, JDK 17+ và khả năng tải dependencies khi chưa có trong cache. Vì Spring là dependency bên ngoài, `javac GenericElementBindingDemo.java` không đủ classpath để biên dịch độc lập.

### Phân tích từng bước của ví dụ

1. `BeanWrapperImpl` đọc metadata của property `quantities`; `getElementTypeDescriptor().getType()` trả `Integer.class`. Với `prices`, `getMapValueTypeDescriptor()` trả `BigDecimal.class`. Đây là thông tin từ **chữ ký property**, không suy ra từ phần tử hiện có.
2. `input` chứa hoàn toàn giá trị chuỗi, tương tự dữ liệu HTTP form. `binder.bind(input)` xử lý từng property path và tìm phần tử đích của JavaBean.
3. Đường dẫn `quantities[0]` và `quantities[1]` dẫn tới element kiểu `Integer` nên Spring dùng converter chuỗi → số nguyên. Danh sách sau binding là `[7, 12]` với kiểu phần tử thật là `Integer`.
4. Đường dẫn `prices[book]` dẫn tới value kiểu `BigDecimal`; `"19.50"` trở thành `BigDecimal` (định dạng in ra giữ phần thập phân là `19.50`).
5. Binder thứ hai nhận `"not-a-number"` cho element `Integer` nên không thể chuyển kiểu; `BindingResult` ghi `FieldError` và `isBindingFailure()` báo `true`. Ví dụ kiểm tra boolean để không phụ thuộc câu mô tả exception vốn có thể khác theo cấu hình.

`setAllowedFields(...)` trong ví dụ chỉ để giới hạn chính xác những property có quyền binding. Trên ứng dụng web, nên thiết kế DTO và allowlist có chủ đích; generic type **không bảo vệ** khỏi mass assignment hoặc những đường dẫn property không mong muốn.

## 5. Vì sao phải cung cấp `TypeDescriptor` khi chuyển một collection bằng tay?

Khi chỉ gọi:

~~~java
conversionService.convert(source, List.class);
~~~

Java truyền vào mỗi `List.class` ở vai trò kiểu đích. Nó **không thể biểu diễn `List<Integer>`** vì tham số generic bị xóa ở cấp đối tượng `Class`. Do đó, kết quả không được đảm bảo đã chuyển từng chuỗi thành `Integer` theo ý muốn. Đây là khác biệt lớn giữa chuyển đổi không có ngữ cảnh và binding vào property đã khai báo generic.

Với `DefaultConversionService`, bạn có thể mô tả rõ kiểu nguồn và kiểu đích bằng `TypeDescriptor`:

~~~java
DefaultConversionService service = new DefaultConversionService();

List<String> source = List.of("3", "8");
TypeDescriptor from = TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(String.class));
TypeDescriptor to = TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(Integer.class));

Object converted = service.convert(source, from, to);
List<?> result = (List<?>) converted;

System.out.println(result);                                  // [3, 8]
System.out.println(result.get(0).getClass().getSimpleName()); // Integer
~~~

Đây là snippet có thể đặt trong một `main` của ứng dụng Java có dependency `spring-core` và import `java.util.List`, `TypeDescriptor`, `DefaultConversionService`. Khi cả hai descriptor xác định rõ kiểu element, `DefaultConversionService` có thể ghép converter collection với converter phần tử `String → Integer`. Kiểu kết quả runtime đã được xác nhận qua `getClass().getSimpleName()`.

Nếu muốn chuyển collection chứa đối tượng tùy chỉnh, cần thêm converter cho kiểu phần tử và chắc chắn rằng converter đó được đăng ký vào service đang dùng. Không mặc định mọi kiểu domain đều tự chuyển được từ String.

## 6. Generic metadata trong List, Map, Array và nested path

### `List<T>` và `Set<T>`

Với `List<Integer>` hoặc `Set<LocalDate>`, khai báo `<T>` cho Spring biết element type. Nếu `String → T` có converter/formatter phù hợp, Spring có thể chuyển các phần tử. List có indexed path như `items[0]`; Set thường không nên được giả định có chỉ số ổn định. Với form gửi nhiều giá trị cho một property, kiểu dữ liệu nguồn (một chuỗi, mảng chuỗi hay collection) và converter được cấu hình quyết định cách chuyển cả collection.

Ví dụ danh sách dùng phần tử enum:

~~~java
enum Priority { LOW, MEDIUM, HIGH }

public class FilterForm {
    private List<Priority> priorities = new ArrayList<>();

    public List<Priority> getPriorities() { return priorities; }
    public void setPriorities(List<Priority> priorities) {
        this.priorities = priorities;
    }
}
~~~

Với đường dẫn `priorities[0]` và giá trị `"HIGH"`, bộ chuyển enum mặc định có thể gán `Priority.HIGH`. Chuỗi không khớp enum có thể tạo lỗi conversion. Khi cho phép nhập không phân biệt chữ hoa/chữ thường hoặc có tên hiển thị riêng, hãy đăng ký converter/formatter phù hợp thay vì tự sửa dữ liệu ngầm.

### `Map<K,V>`

Với `Map<String, BigDecimal>`, `prices[book]` cần metadata của **value type**. Với `Map<Long, Integer>`, một mapped property còn có metadata của **key type**. Để chuyển `"42"` thành `Long 42L` và giá trị `"5"` thành `Integer 5`, service cần cả hai converter thích hợp.

~~~java
public class LimitsForm {
    private Map<Long, Integer> limits = new LinkedHashMap<>();

    public Map<Long, Integer> getLimits() { return limits; }
    public void setLimits(Map<Long, Integer> limits) {
        this.limits = limits;
    }
}
~~~

Trong bối cảnh binder hỗ trợ key conversion, `limits[42]` trỏ tới entry key số `42L`. Chú ý các quy tắc chuyển map key phức tạp hơn khi dùng key là đối tượng nghiệp vụ; không dựa vào dạng `toString()` của domain object nếu chưa định nghĩa converter rõ ràng.

### Array

`Integer[] quantities` khai báo component type trực tiếp qua Java array type (khác với tham số generic của `List<Integer>`). Spring có thể dùng bộ chuyển kiểu phần tử tương ứng khi binding array. Việc mở rộng hoặc ghi chỉ số vượt kích thước cần được xử lý theo đặc tính array và cấu hình binder.

### Nested object

Với `List<OrderLine> lines` và `OrderLine.quantity` có kiểu `Integer`, đường dẫn `lines[0].quantity` sử dụng metadata của hai tầng: list element là `OrderLine` và JavaBean property bên trong là `Integer`. Nó khác `lines[0]`: một đường dẫn yêu cầu gán **một field số**; đường dẫn còn lại có thể yêu cầu chuyển **một chuỗi thành cả đối tượng OrderLine**, thường cần converter riêng.

Một nested path chỉ bind được khi đường dẫn hợp lệ và các thành phần cần thiết có thể truy cập/tạo. Nếu collection rỗng, cần xác định rõ chính sách auto-grow và giới hạn số phần tử; nếu đối tượng con trừu tượng, interface hoặc có constructor đặc biệt, Spring có thể không tự tạo được nó.

## 7. Cấu hình converter tùy chỉnh cho kiểu phần tử của ứng dụng

Giả sử một danh sách khai báo `List<Sku> skus`, trong đó `Sku` là kiểu nghiệp vụ. Spring không nhất thiết hiểu quy tắc chuẩn hóa mã sản phẩm, nên bạn có thể đăng ký converter `String → Sku`:

~~~java
record Sku(String value) {}

final class StringToSkuConverter
        implements org.springframework.core.convert.converter.Converter<String, Sku> {

    @Override
    public Sku convert(String source) {
        String normalized = source.trim().toUpperCase(java.util.Locale.ROOT);
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("SKU không được trống");
        }
        return new Sku(normalized);
    }
}
~~~

Đây là snippet của dự án Java 17+, không phải một chương trình main độc lập. Tại chỗ cấu hình conversion service:

~~~java
DefaultConversionService service = new DefaultConversionService();
service.addConverter(new StringToSkuConverter());
binder.setConversionService(service);
~~~

Nếu `binder` đang bind vào property `List<Sku>` và đường dẫn tới phần tử (ví dụ `skus[0]`), Spring có thể tái sử dụng converter đó để chuyển từng chuỗi sang `Sku`. Với ví dụ trên, input `" ab-12 "` tạo `new Sku("AB-12")`.

Trong Spring MVC, cách phổ biến là đăng ký converter bằng `WebMvcConfigurer.addFormatters(FormatterRegistry registry)` (hoặc cấu hình tương đương) để bộ chuyển đổi được dùng bởi tầng MVC:

~~~java
@Configuration
class WebConversionConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToSkuConverter());
    }
}
~~~

Snippet cấu hình này cần imports `org.springframework.context.annotation.Configuration`, `org.springframework.web.servlet.config.annotation.WebMvcConfigurer` và `org.springframework.format.FormatterRegistry`, đồng thời `StringToSkuConverter` phải khả dụng trong project. Khi một Spring Boot/MVC application đã có conversion service do framework cấu hình, hãy **bổ sung converter vào registry phù hợp**, không tự thay toàn bộ service khiến các converter mặc định biến mất.

Với dữ liệu ngày/giờ, tiền tệ, số theo locale, `Formatter` hoặc conversion service chứa formatters có thể phù hợp hơn converter chỉ nhận chuỗi. Generic metadata xác định loại phần tử; **cách phân tích biểu diễn chuỗi** còn phụ thuộc converter/formatter, locale và configuration.

## 8. Kết quả lỗi khi một phần tử không chuyển kiểu được

Nếu giá trị của `quantities[1]` là `"abc"` nhưng element type là `Integer`, `DataBinder` thường tạo `FieldError` trong `BindingResult`. Có thể kiểm tra mà không để exception kỹ thuật lọt ra UI:

~~~java
BindingResult bindingResult = binder.getBindingResult();

if (bindingResult.hasErrors()) {
    for (FieldError error : bindingResult.getFieldErrors()) {
        System.out.println(error.getField());            // Ví dụ: quantities[1]
        System.out.println(error.getCode());             // Thường: typeMismatch
        System.out.println(error.isBindingFailure());    // true khi binding hỏng
    }
}
~~~

Đoạn này minh họa sau `binder.bind(...)`, cần import `BindingResult` và `FieldError`. Mã có thể là `typeMismatch` với các mã cụ thể hơn theo property path và object name, tùy `MessageCodesResolver`. Ví dụ resource bundle có thể định nghĩa:

~~~properties
typeMismatch.orderForm.quantities[1]=Số lượng thứ hai phải là số nguyên hợp lệ.
typeMismatch.quantities=Giá trị số lượng không đúng định dạng.
typeMismatch=Giá trị không thể chuyển sang kiểu yêu cầu.
~~~

Để chọn thông báo phù hợp, dùng `MessageSource.getMessage(fieldError, locale)` và kiểm tra các ứng viên `getCodes()`. Khi tên field có chỉ số, mã chi tiết được phân giải có thể khác nhau theo resolver; hãy kiểm tra codes thực tế thay vì khẳng định một key chắc chắn được ưu tiên ở mọi cấu hình.

**Chuyển kiểu và validation là hai bước khác nhau:**

- `quantities[1]="abc"`: không chuyển thành `Integer`, lỗi binding.
- `quantities[1]="-3"`: chuyển thành `Integer -3` thành công, nhưng có thể vi phạm `@Positive` hoặc quy tắc nghiệp vụ.
- `quantities[1]="3"`: chuyển được, song vẫn cần xét các ràng buộc khác nếu được định nghĩa.

Generic type không tự kích hoạt `@Positive` hay Bean Validation. Nếu dùng container element constraints như `List<@Positive Integer>`, cần provider Jakarta Bean Validation tương thích, validation được kích hoạt trong luồng thích hợp và quy tắc được cấu hình đúng.

Một lỗi chuyển kiểu tại phần tử có thể làm field cụ thể chưa được gán như kỳ vọng; trạng thái các phần tử khác phụ thuộc việc binder xử lý các property value còn lại. Không mặc định rằng cả collection sẽ rollback atomically nếu một phần tử thất bại. Trong luồng web, chỉ tiếp tục nghiệp vụ khi kiểm tra toàn bộ `BindingResult.hasErrors()`.

## 9. Kiểm tra khi metadata generic không được phân giải

Nếu một list chứa giá trị dạng `String` dù tác giả mong `Integer`, nên kiểm tra lần lượt:

1. **Chữ ký JavaBean:** property là `List<Integer>` thật hay bị khai báo raw `List`, `List<?>` hoặc `Object`? Getter và setter có cùng kiểu không?
2. **Property path:** `quantities[0]` trỏ vào danh sách kiểu Integer, còn `quantities` trỏ vào toàn bộ container; cách chuyển có thể khác nhau.
3. **Metadata do Spring nhìn thấy:** dùng `BeanWrapper.getPropertyTypeDescriptor("quantities")` và `getElementTypeDescriptor()` để xem generic có xác định hay không. `TypeDescriptor` có thể trả `null` ở nơi không giải quyết được loại phần tử.
4. **ConversionService:** đối tượng `DataBinder` đang dùng đã được set `ConversionService` chưa? Ứng dụng MVC/Boot có registry riêng không? Đã thêm converter cho kiểu domain chưa?
5. **Giá trị nguồn:** request gửi một String, `String[]`, JSON hay một List? Ngữ cảnh HTTP converter/Jackson khác với property binding của `DataBinder`.
6. **Lỗi đã ghi:** đọc `getFieldErrors()`, `getCodes()`, `isBindingFailure()`; không dựa vào câu thông báo exception làm bằng chứng duy nhất.
7. **Cấu trúc collection:** list/map đã có thể ghi hay chưa? Có giá trị immutable không? Chỉ số có vượt giới hạn auto-grow hoặc key không có converter không?
8. **Phạm vi bind:** field có nằm trong `allowedFields` không? Có bị suppressed do cơ chế phòng mass assignment không?

Raw type làm ví dụ dễ sai:

~~~java
// Thiếu thông tin phần tử: tránh dùng trong form model.
private List quantities;

// Có thông tin để Spring phân giải element type.
private List<Integer> quantities;
~~~

Ngoài ra, khi chuyển bằng API lập trình, chỉ cung cấp `List.class` cũng đánh mất loại phần tử đích. Hãy dùng `TypeDescriptor.collection(...)`, hoặc phản chiếu `TypeDescriptor` từ một property đã khai báo generic.

### Kiểm tra nested/indexed path an toàn

Khi bind các đường dẫn như `lines[5000].quantity`, dữ liệu từ client có thể làm binder phải tạo nhiều phần tử. Spring có giới hạn auto-grow collection (có thể cấu hình) và cơ chế cho phép/cấm field. Với dữ liệu do người dùng kiểm soát, giới hạn kích thước đầu vào, số lượng phần tử và field được bind. Không tăng vô hạn các giới hạn chỉ để làm mất lỗi. Ưu tiên request DTO với cấu trúc và giới hạn rõ ràng.

Với map, nếu key chứa ký tự đặc biệt, cú pháp property path và quy tắc escape cần được kiểm thử; không ghép raw text bất kỳ vào `[...]` mà không xác nhận đúng cú pháp và chính sách cho phép binding.

## 10. Kịch bản thực hành và xác nhận kết quả

| Đầu vào | Khai báo đích | Kỳ vọng |
| --- | --- | --- |
| `quantities[0]="7"` | `List<Integer>` | Phần tử 0 là `Integer 7` |
| `prices[book]="19.50"` | `Map<String,BigDecimal>` | Entry `"book"` chứa `BigDecimal("19.50")` |
| `quantities[1]="abc"` | `List<Integer>` | Có `FieldError` về conversion, thường `typeMismatch` |
| `quantities[1]="-3"` | `List<Integer>` | Conversion đạt; validation riêng có thể từ chối giá trị |
| `priorities[0]="HIGH"` | `List<Priority>` | Converter enum phù hợp tạo `Priority.HIGH` |
| `skus[0]=" ab-12 "` | `List<Sku>` và `StringToSkuConverter` | Tạo phần tử `Sku("AB-12")` |
| Chuyển `List<String>` sang `List<Integer>` không có JavaBean | `TypeDescriptor.collection(List.class, Integer)` | ConversionService biết element type khi descriptor đầy đủ |
| Property raw `List` | Không khai báo element type | Không có bảo đảm chuyển sang loại phần tử mong muốn |

Một bài kiểm tra tự động nên xác nhận **kiểu runtime của phần tử** chứ không chỉ so sánh chuỗi `toString()`. Ví dụ `List.of("7","12").toString()` và `List.of(7,12).toString()` trông đều giống `[7, 12]`, nhưng kiểu dữ liệu rất khác nhau. Dùng `getClass()` hoặc assertion `instanceof` trên phần tử, và kiểm tra cả `BindingResult`. Tách test generic metadata, conversion thành công, conversion lỗi và validation riêng sẽ chỉ ra chính xác bước nào gây lỗi.

## 11. Những nhầm lẫn thường gặp

1. **“List đã là generic nên JVM tự đổi String thành Integer.”** JVM không tự chuyển kiểu giá trị; Spring cần metadata đích và converter thích hợp.
2. **“Chỉ cần `convert(value, List.class)`.”** `Class<List>` không mang `<Integer>`; hãy dùng `TypeDescriptor` hoặc binding vào JavaBean có generic signature.
3. **“Property `quantities` và `quantities[0]` giống nhau.”** Một bên là cả container, bên kia là element; metadata và đường chuyển có thể khác.
4. **“Mọi property path đều được tự mở rộng.”** Auto-grow có điều kiện, giới hạn và không thể tạo mọi kiểu object hoặc collection.
5. **“Đổi được kiểu nghĩa là dữ liệu hợp lệ.”** Validation cần chạy riêng; `Integer -3` vẫn có thể vi phạm `@Positive`.
6. **“Lỗi không convert sẽ tự ném ra màn hình.”** Trong property binding qua `DataBinder`, lỗi thường được lưu vào `BindingResult`; phải kiểm tra và đưa ra thông báo có kiểm soát.
7. **“Mã lỗi field chỉ có một chuỗi.”** `FieldError.getCodes()` chứa các ứng viên cho resolution; `getCode()` thường là code tổng quát nhất.
8. **“Generic đủ để ngăn request gán field nguy hiểm.”** Generic kiểm soát kiểu dữ liệu, còn giới hạn binding/DTO/validation kiểm soát phạm vi và quy tắc.
9. **“Mọi chuỗi thời gian/số được phân tích giống nhau ở mọi locale.”** Bộ formatter, locale và cấu hình của Spring MVC có thể ảnh hưởng định dạng.
10. **“Bất kỳ JSON nào cũng đi qua `DataBinder` như form.”** `@RequestBody` thường deserialize qua `HttpMessageConverter`/Jackson; generic type vẫn quan trọng nhưng đường conversion và exception khác.

## 12. Tóm tắt cách áp dụng trong dự án

Khi định nghĩa form/DTO có collection hoặc map, hãy giữ **khai báo generic cụ thể**, cho Spring truy cập một property path hợp lệ, cấu hình `ConversionService`/`FormatterRegistry` cho các element type được hỗ trợ và kiểm tra `BindingResult`. Đối với chuyển đổi collection bằng API riêng, truyền `TypeDescriptor` có element/key/value type cụ thể. Chỉ sau khi conversion thành công mới xét các ràng buộc validation phù hợp.

Nguồn tham khảo: [Spring Framework 6.2 – Data Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beans-beans.html), [Spring Framework – Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html), [TypeDescriptor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/TypeDescriptor.html).
