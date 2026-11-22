# Đăng ký PropertyEditor theo kiểu hoặc đường dẫn thuộc tính trong Spring Framework

## 1. Vì sao phải chọn phạm vi đăng ký editor?

Khi Spring đưa dữ liệu đầu vào vào một JavaBean, giá trị bên ngoài thường là chuỗi, còn property đích có thể là `LocalDate`, `Integer`, `Date`, kiểu miền nghiệp vụ tự định nghĩa hoặc một collection. **PropertyEditor** là cơ chế JavaBeans giúp chuyển một biểu diễn bằng văn bản thành giá trị Java mà setter/constructor có thể nhận.

Spring hỗ trợ **hai phạm vi đăng ký custom editor**:

1. **Theo kiểu (`requiredType`):** một editor được dùng cho các property có kiểu tương ứng trong phạm vi registry/binder đó.
2. **Theo đường dẫn (`propertyPath`):** một editor được gắn với một property cụ thể, chẳng hạn `"delivery.shipOn"`, để xử lý khác các property cùng kiểu.

Ví dụ model có hai trường cùng `LocalDate`:

```text
OrderForm
├── createdOn: LocalDate       <-- chuỗi ISO: 2026-11-02
└── delivery: Delivery
    └── shipOn: LocalDate      <-- chuỗi ngày/tháng/năm: 03/11/2026
```

Nếu đăng ký một editor cho toàn bộ `LocalDate.class`, cả hai trường dùng cùng quy tắc chuyển kiểu. Nhưng `shipOn` cần định dạng khác `createdOn`. Ta có thể đăng ký editor chung cho kiểu `LocalDate` và **editor riêng cho đường dẫn `delivery.shipOn`**. Khi bind đúng đường dẫn, editor của property cụ thể được ưu tiên so với editor chung theo kiểu.

Đây là hành vi trong **Spring PropertyEditorRegistry**, dùng được qua `BeanWrapperImpl`, `DataBinder` hoặc `WebDataBinder`. Nó khác với annotation validation: editor xử lý **biểu diễn/kiểu dữ liệu**, còn validator kiểm tra **tính hợp lệ theo quy tắc**.

## 2. API trung tâm: PropertyEditorRegistry

Interface `org.springframework.beans.PropertyEditorRegistry` khai báo hai overload quan trọng:

```java
void registerCustomEditor(
        Class<?> requiredType,
        java.beans.PropertyEditor propertyEditor);

void registerCustomEditor(
        Class<?> requiredType,
        String propertyPath,
        java.beans.PropertyEditor propertyEditor);
```

Chữ ký trên được rút gọn để minh họa, bỏ qua nullable annotations. Các implementation đáng chú ý gồm `BeanWrapperImpl`, `DataBinder` và `WebDataBinder`.

| Cách gọi | Phạm vi đăng ký | Trường hợp sử dụng |
| --- | --- | --- |
| `registerCustomEditor(LocalDate.class, editor)` | Tất cả property kiểu `LocalDate` mà registry đang xử lý | Mọi ngày theo cùng định dạng ISO |
| `registerCustomEditor(LocalDate.class, "delivery.shipOn", editor)` | Riêng `delivery.shipOn` | Ngày giao hàng dùng `dd/MM/uuuu` |
| `registerCustomEditor(String.class, "displayName", editor)` | Riêng chuỗi `displayName` | Trim/chuẩn hóa tên hiển thị |
| `registerCustomEditor(String.class, editor)` | Mọi property `String` | Chuẩn hóa chuỗi mặc định, nếu thực sự muốn |
| `registerCustomEditor(null, "delivery.shipOn", editor)` | Đăng ký theo path, không khai báo kiểu | Hợp lệ trong những trường hợp scalar có path rõ ràng; nên nêu kiểu nếu biết |

**`requiredType`** là kiểu Java của property hoặc của phần tử collection nếu đăng ký theo phần tử. **`propertyPath`** là tên property tương đối với **đối tượng đang được bind/bọc**, không phải URL và không tự thêm model attribute name.

Ví dụ bean đích là `orderForm` trong controller. Tên path đúng thường là:

```text
delivery.shipOn
```

Không tự biến thành `orderForm.delivery.shipOn` chỉ vì `@ModelAttribute("orderForm")` có tên như vậy. Path phải khớp cấu trúc property mà binder thực sự nhìn thấy.

Với overload hai đối số, bắt buộc có `requiredType` và không chỉ định path. Với overload ba đối số, Spring cho phép kiểu hoặc path được cung cấp theo quy tắc API. Đối với collection/array, **nên luôn ghi rõ kiểu** để Spring biết editor chuyển đổi cả collection hay từng phần tử.

### Scope của registry

Đăng ký vào `new BeanWrapperImpl(bean)` chỉ ảnh hưởng wrapper ấy. Đăng ký vào `new DataBinder(bean)` chỉ ảnh hưởng binder ấy. Đăng ký trong một phương thức `@InitBinder` của Spring MVC áp dụng cho những binder thuộc phạm vi controller/model attribute liên quan. Nó không tự trở thành quy tắc parse toàn ứng dụng hay quy tắc chuyển JSON bằng Jackson.

## 3. Spring chọn editor nào khi cùng có type và path?

Giả sử có hai đăng ký:

```java
wrapper.registerCustomEditor(
        LocalDate.class, new IsoDateEditor());

wrapper.registerCustomEditor(
        LocalDate.class, "delivery.shipOn",
        new DayMonthYearEditor());
```

Khi Spring cần đổi giá trị cho `createdOn` (cũng là `LocalDate`), không có đăng ký riêng theo `createdOn` nên nó dùng `IsoDateEditor` theo kiểu. Khi cần đổi `delivery.shipOn`, có đăng ký theo path nên dùng `DayMonthYearEditor`.

Cách hiểu thực tế:

```text
convert(raw="2026-11-02", target=LocalDate, path="createdOn")
  -> tìm editor riêng cho path "createdOn": không có
  -> tìm editor theo type LocalDate: IsoDateEditor
  -> LocalDate(2026-11-02)

convert(raw="03/11/2026", target=LocalDate, path="delivery.shipOn")
  -> tìm editor riêng cho path: DayMonthYearEditor
  -> LocalDate(2026-11-03)
```

**Đường dẫn cụ thể có thể ghi đè quy tắc chung theo kiểu trong quá trình tra cứu.** Đừng dựa vào thứ tự `HashMap` của input hay thứ tự khai báo field để đoán editor được chọn. Hãy xác nhận bằng kết quả binding và kiểm thử khi bạn đăng ký nhiều quy tắc.

Cơ chế Spring phân biệt một editor tự đăng ký với **default editors** được cung cấp sẵn bởi `BeanWrapperImpl` và các conversion services đang cấu hình. Một custom editor được chọn cho một property cụ thể có thể thay đổi hành vi mặc định của property ấy. Vì thế, càng đăng ký rộng theo kiểu, phạm vi tác động càng lớn.

## 4. Ví dụ Java 17+ chạy được: một editor chung, một editor theo path

Ví dụ này dùng **Spring Framework 6.2.x**, Java 17+ và Maven, không cần Spring Boot hay HTTP server. Mục tiêu là thấy hai property `LocalDate` dùng hai định dạng khác nhau nhưng vẫn được lưu thành cùng một kiểu Java.

### 4.1. pom.xml

Tạo file `pom.xml` ở thư mục dự án Maven:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>property-editor-scope-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-beans</artifactId>
            <version>6.2.12</version>
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
```

`spring-beans` cung cấp `BeanWrapperImpl` và kéo theo các dependency Spring Core cần thiết. Không cần `spring-boot-starter-web` để sử dụng wrapper trực tiếp.

### 4.2. Một file Java hoàn chỉnh

Tạo file `src/main/java/demo/EditorScopeDemo.java`:

```java
package demo;

import java.beans.PropertyEditorSupport;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

import org.springframework.beans.BeanWrapperImpl;

public class EditorScopeDemo {

    public static class Delivery {
        private LocalDate shipOn;

        public Delivery() {}

        public LocalDate getShipOn() {
            return shipOn;
        }

        public void setShipOn(LocalDate shipOn) {
            this.shipOn = shipOn;
        }
    }

    public static class OrderForm {
        private LocalDate createdOn;
        private Delivery delivery = new Delivery();

        public OrderForm() {}

        public LocalDate getCreatedOn() {
            return createdOn;
        }

        public void setCreatedOn(LocalDate createdOn) {
            this.createdOn = createdOn;
        }

        public Delivery getDelivery() {
            return delivery;
        }

        public void setDelivery(Delivery delivery) {
            this.delivery = delivery;
        }
    }

    public static class IsoDateEditor extends PropertyEditorSupport {
        @Override
        public void setAsText(String text) {
            setValue(LocalDate.parse(text.trim()));
        }

        @Override
        public String getAsText() {
            LocalDate value = (LocalDate) getValue();
            return value == null ? "" : value.toString();
        }
    }

    public static class DayMonthYearEditor
            extends PropertyEditorSupport {

        private static final DateTimeFormatter FORMAT =
                DateTimeFormatter.ofPattern(
                        "dd/MM/uuuu", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        @Override
        public void setAsText(String text) {
            setValue(LocalDate.parse(text.trim(), FORMAT));
        }

        @Override
        public String getAsText() {
            LocalDate value = (LocalDate) getValue();
            return value == null ? "" : value.format(FORMAT);
        }
    }

    public static void main(String[] args) {
        OrderForm form = new OrderForm();
        BeanWrapperImpl wrapper = new BeanWrapperImpl(form);

        // Áp dụng cho các property LocalDate nói chung.
        wrapper.registerCustomEditor(
                LocalDate.class, new IsoDateEditor());

        // Chỉ áp dụng cho property lồng nhau này.
        wrapper.registerCustomEditor(
                LocalDate.class, "delivery.shipOn",
                new DayMonthYearEditor());

        wrapper.setPropertyValue("createdOn", "2026-11-02");
        wrapper.setPropertyValue(
                "delivery.shipOn", "03/11/2026");

        System.out.println(
                "createdOn=" + form.getCreatedOn());
        System.out.println(
                "delivery.shipOn="
                        + form.getDelivery().getShipOn());
        System.out.println(
                "sameTarget="
                        + (wrapper.getWrappedInstance() == form));
    }
}
```

### 4.3. Lệnh chạy và kết quả

Trong thư mục chứa `pom.xml`, có Maven và JDK 17+:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=demo.EditorScopeDemo
```

Stdout từ `main` (không kể log Maven):

```text
createdOn=2026-11-02
delivery.shipOn=2026-11-03
sameTarget=true
```

Lý do:

1. Cả `createdOn` và `delivery.shipOn` đều là `LocalDate`, có getter/setter JavaBeans.
2. Đối với `createdOn`, quy tắc theo kiểu `LocalDate.class` chọn `IsoDateEditor`. Chuỗi ISO được parse thành ngày `2026-11-02`.
3. Đối với `delivery.shipOn`, quy tắc theo path chọn `DayMonthYearEditor`. Chuỗi `03/11/2026` được parse theo ngày/tháng/năm, cho `2026-11-03`.
4. `Delivery` đã được khởi tạo trong `OrderForm`, nên nested property có object trung gian; ví dụ không cần bật auto-grow.
5. `sameTarget=true` cho thấy wrapper cập nhật trực tiếp object `form`, không tạo bản sao.

Ở đây `PropertyEditorSupport.setAsText(...)` chịu trách nhiệm chuyển chuỗi thành giá trị đích thông qua `setValue(...)`. `getAsText()` hỗ trợ chiều ngược lại khi một thành phần cần biểu diễn object dưới dạng văn bản; output của ví dụ dùng `LocalDate.toString()` trực tiếp nên không phụ thuộc vào cách gọi `getAsText()`.

**Giới hạn ví dụ:** `LocalDate.parse(...)` sẽ ném lỗi với chuỗi sai định dạng. Chương trình chủ động dùng dữ liệu hợp lệ để minh họa việc chọn editor. Khi xử lý input web, dùng `WebDataBinder` để gom lỗi chuyển kiểu vào `BindingResult` theo ngữ cảnh thích hợp.

## 5. Đăng ký trực tiếp trên DataBinder và lấy BindingResult

Trong ứng dụng nhận nhiều input, `DataBinder` giúp kết hợp property binding, type conversion và ghi nhận lỗi. Không phải tự bắt exception cho từng setter khi đang bind nhiều field.

Ví dụ dưới đây **được đặt trong một method**, sử dụng các class `OrderForm`, `IsoDateEditor` và `DayMonthYearEditor` ở ví dụ trên:

```java
import java.util.Map;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;
import org.springframework.validation.BindingResult;

OrderForm form = new OrderForm();
DataBinder binder = new DataBinder(form, "orderForm");

// Chỉ cho phép hai key của ví dụ khi dùng nguồn không đáng tin cậy.
binder.setAllowedFields("createdOn", "delivery.shipOn");

binder.registerCustomEditor(
        java.time.LocalDate.class, new IsoDateEditor());
binder.registerCustomEditor(
        java.time.LocalDate.class, "delivery.shipOn",
        new DayMonthYearEditor());

binder.bind(new MutablePropertyValues(Map.of(
        "createdOn", "2026-11-02",
        "delivery.shipOn", "03/11/2026")));

BindingResult errors = binder.getBindingResult();

if (errors.hasErrors()) {
    System.out.println("Binding failed");
} else {
    System.out.println(form.getCreatedOn());
    System.out.println(form.getDelivery().getShipOn());
}
```

Kết quả kỳ vọng của phần `else`:

```text
2026-11-02
2026-11-03
```

Đoạn này có các import của những class `EditorScopeDemo` lồng nhau cần điều chỉnh theo nơi đặt code; nó là snippet **không tự biên dịch riêng lẻ** nếu chưa đưa vào class/method cùng các type. Luồng chính là **đăng ký trước khi gọi `bind(...)`**, sau đó đọc `BindingResult`.

Nếu `"delivery.shipOn"` nhận `"31/02/2026"`, editor ngày/tháng/năm không parse thành ngày hợp lệ. Trong quá trình property binding, `DataBinder` thường ghi một `FieldError` có mã liên quan `typeMismatch`. Kiểm tra:

```java
BindingResult result = binder.getBindingResult();
if (result.hasFieldErrors("delivery.shipOn")) {
    System.out.println("Invalid delivery date");
}
```

Đây cũng là snippet trong method. `DataBinder` ghi nhận lỗi binding; **chưa đồng nghĩa đã chạy Bean Validation** như `@NotNull`, `@Future`. Muốn kiểm tra constraint, cấu hình và gọi validator (hoặc dùng `@Valid` trong MVC) riêng.

## 6. Đăng ký qua @InitBinder trong Spring MVC

Khi sử dụng Spring MVC, `WebDataBinder` được framework tạo cho việc gắn request parameters vào `@ModelAttribute`. Thay vì tạo binder thủ công, đặt cấu hình editor trong một method `@InitBinder`.

Ví dụ controller (đây là **mẫu tích hợp**; model `OrderForm` và editor classes nằm trong project như phần 4, cần các dependencies Spring MVC/validation tương ứng):

```java
import java.time.LocalDate;

import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

@Controller
public class OrderController {

    @InitBinder("orderForm")
    void initOrderBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "createdOn", "delivery.shipOn");

        binder.registerCustomEditor(
                LocalDate.class, new IsoDateEditor());

        binder.registerCustomEditor(
                LocalDate.class, "delivery.shipOn",
                new DayMonthYearEditor());
    }

    @PostMapping("/orders")
    public String save(
            @ModelAttribute("orderForm") OrderForm orderForm,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "order-form";
        }

        // Service xử lý tiếp nếu form hợp lệ.
        return "order-success";
    }
}
```

**Cách áp dụng đúng:** Đặt `OrderController` vào file `OrderController.java` trong package phù hợp, thêm import/định nghĩa cho `OrderForm`, `IsoDateEditor`, `DayMonthYearEditor` và các view `order-form` / `order-success`. Trong ví dụ, `BindingResult` đứng **ngay sau** tham số `@ModelAttribute` để nhận lỗi binding. Cần bổ sung `@Valid` và provider nếu muốn kiểm tra Jakarta Bean Validation; bản thân property editor chỉ chuyển kiểu.

Form có thể gửi:

```text
createdOn=2026-11-02&delivery.shipOn=03%2F11%2F2026
```

Key phải khớp property path đã khai báo. `@InitBinder("orderForm")` chỉ nhắm đến binder của model attribute có tên `"orderForm"` trong ngữ cảnh controller; `@InitBinder` không có tên có phạm vi rộng hơn trong controller. `@ControllerAdvice` có thể khai báo `@InitBinder` dùng chung cho nhiều controller, nhưng cần thận trọng với tên model và tác động lên nhiều request.

Lưu ý: Editor của `@ModelAttribute` dùng trong data binding form/query; **`@RequestBody` JSON** thường đi qua `HttpMessageConverter`, chẳng hạn Jackson, chứ không tự sử dụng editor này để parse từng thuộc tính JSON.

## 7. Nested path và indexed property: tên phải đúng

Path có thể là:

| Property path | Mục tiêu |
| --- | --- |
| `startDate` | Property `startDate` của object đích |
| `delivery.shipOn` | Property `shipOn` trên bean `delivery` |
| `customer.address.postalCode` | Property nested nhiều cấp |
| `items[0].quantity` | Field của phần tử index 0 |
| `items[2].quantity` | Field của phần tử index 2 |
| `settings[region]` | Giá trị trong Map theo key |
| `tags` | Toàn bộ collection/list nếu property `tags` là collection |

Với danh sách, có một chi tiết quan trọng trong Javadoc của `PropertyEditorRegistry`:

> Để đăng ký editor cho `items[n].quantity` ở mọi index `n`, có thể sử dụng tên path `items.quantity`.

Ví dụ:

```java
binder.registerCustomEditor(
        Integer.class, "items.quantity",
        new CustomNumberEditor(Integer.class, false));
```

Snippet cần import `org.springframework.beans.propertyeditors.CustomNumberEditor`, nằm trong method có `binder`. Đăng ký này thể hiện mục tiêu áp dụng quy tắc cho field `quantity` của các phần tử `items` (giả sử type và cấu trúc model phù hợp); Spring có cơ chế canonical/matching path xử lý index. Không tự đưa dấu sao `items[*].quantity` hoặc ký hiệu `items[n].quantity` làm chuỗi đăng ký nếu API không định nghĩa wildcard theo cách đó. Đối với các biến thể path phức tạp, xác nhận với unit test theo phiên bản Spring đang dùng.

### Editor cho collection hay editor cho phần tử?

Giả sử `OrderForm` có `List<LocalDate> holidays`. Hai yêu cầu hoàn toàn khác nhau:

1. Parse **một chuỗi hoặc object input** thành **toàn bộ `List<LocalDate>`**.
2. Parse **từng chuỗi phần tử** thành một `LocalDate` nằm trong list.

Cần chỉ rõ `requiredType` và path tương ứng:

```java
// Editor phải có khả năng tạo cả List; đây là minh họa API.
binder.registerCustomEditor(
        java.util.List.class, "holidays", wholeListEditor);

// Editor phải tạo LocalDate cho từng phần tử.
binder.registerCustomEditor(
        java.time.LocalDate.class, "holidays",
        oneDateEditor);
```

Hai dòng trên là **hai cách thiết kế thay thế**, không đăng ký đồng thời cho cùng `holidays`. Các biến `wholeListEditor`/`oneDateEditor` đại diện implementation `PropertyEditor` do project xây dựng; đây không phải snippet Java độc lập. Theo tài liệu Spring, nếu path chỉ tới array/collection, editor có thể được áp dụng cho **cả collection** hoặc **các phần tử**, tùy `requiredType`. Spring cảnh báo **chỉ hỗ trợ một custom editor trên mỗi property path**, nên không đăng ký vừa kiểu collection vừa kiểu phần tử tại cùng path.

Đặc biệt, **không để `requiredType = null` đối với array/collection** vì khi đó rất khó thể hiện rõ editor dành cho container hay element.

## 8. Các PropertyEditor có sẵn đáng biết

Không phải mọi editor phải tự viết từ `PropertyEditorSupport`. Spring cung cấp nhiều editor trong package `org.springframework.beans.propertyeditors`:

| Editor | Mục đích | Ghi chú |
| --- | --- | --- |
| `StringTrimmerEditor` | Loại bỏ khoảng trắng đầu/cuối; có thể đổi chuỗi rỗng thành `null` | Không tự đăng ký mặc định |
| `CustomDateEditor` | Parse/format `java.util.Date` bằng `DateFormat` | Đăng ký khi cần; khác `LocalDate` |
| `CustomNumberEditor` | Parse/format một số `Number` subclasses | Có thể chỉnh hành vi number |
| `CustomBooleanEditor` | Parse boolean với quy tắc cho phép tùy chỉnh | Spring có default editor nhưng có thể override |
| `CustomCollectionEditor` | Chuyển collection sang kiểu collection đích | Phải xem rõ kiểu phần tử/collection |
| `ClassEditor` | Chuyển tên class sang `Class<?>` | Thường có sẵn |
| `LocaleEditor` | Parse/format `Locale` | Thường có sẵn |
| `PatternEditor` | Parse regex `Pattern` | Có trường hợp được hỗ trợ sẵn |

Ví dụ chỉ trim một thuộc tính `displayName`:

```java
import org.springframework.beans.propertyeditors.StringTrimmerEditor;

// Trong @InitBinder hoặc method có binder:
binder.registerCustomEditor(
        String.class, "displayName",
        new StringTrimmerEditor(true));
```

`true` nghĩa là sau khi trim, chuỗi rỗng có thể thành `null`. Phạm vi path giúp tránh trim tự động các property `String` khác mà ứng dụng cần giữ nguyên, như mật khẩu hay chuỗi có khoảng trắng có ý nghĩa.

Nếu muốn trim tất cả `String` ở một binder:

```java
binder.registerCustomEditor(
        String.class, new StringTrimmerEditor(false));
```

`false` giữ chuỗi trống sau khi trim là `""` thay vì đổi sang `null`. Nhưng đăng ký rộng như vậy tác động nhiều property, nên cần đánh giá ý nghĩa của dữ liệu. **Không mặc định rằng mọi chuỗi đều nên trim.**

### Date cũ và Date/Time API mới

`CustomDateEditor` của Spring làm việc với `java.util.Date`; không dùng `CustomDateEditor` để parse trực tiếp property kiểu `LocalDate`. Với `java.time.LocalDate`, thường dùng `Formatter` hoặc `Converter` (và `@DateTimeFormat` nếu tích hợp web phù hợp), hoặc editor tự viết như ví dụ chính nếu thực sự cần PropertyEditor API.

Ví dụ date editor cho `java.util.Date` ở một controller:

```java
import java.text.SimpleDateFormat;
import java.util.Date;
import org.springframework.beans.propertyeditors.CustomDateEditor;

SimpleDateFormat formatter =
        new SimpleDateFormat("yyyy-MM-dd");
formatter.setLenient(false);

binder.registerCustomEditor(
        Date.class, "birthDate",
        new CustomDateEditor(formatter, true));
```

Snippet này ở trong method `@InitBinder` (cần `binder` hợp lệ). `true` cho phép giá trị rỗng thay vì bắt buộc một ngày; khi parse ngày sai vẫn có lỗi phù hợp. `SimpleDateFormat` có trạng thái mutable, vì vậy hãy tạo instance riêng cho binder thay vì share singleton qua nhiều request.

## 9. PropertyEditorRegistrar để tái sử dụng cấu hình

Nếu nhiều controller cần cùng bộ quy tắc, việc sao chép nhiều lần `registerCustomEditor(...)` sẽ khó bảo trì. Spring có interface `PropertyEditorRegistrar`:

```java
package demo;

import java.time.LocalDate;
import org.springframework.beans.PropertyEditorRegistrar;
import org.springframework.beans.PropertyEditorRegistry;

public final class OrderEditorRegistrar
        implements PropertyEditorRegistrar {

    @Override
    public void registerCustomEditors(
            PropertyEditorRegistry registry) {

        registry.registerCustomEditor(
                LocalDate.class, new IsoDateEditor());

        registry.registerCustomEditor(
                LocalDate.class, "delivery.shipOn",
                new DayMonthYearEditor());
    }
}
```

Đoạn trên là **class mẫu**, yêu cầu hai custom editor classes đã định nghĩa trong project; nếu editor là nested classes ở `EditorScopeDemo`, cần import hoặc dùng tên đầy đủ. `OrderEditorRegistrar` không tự chạy `bind(...)`: nó chỉ đăng ký editor trên registry được truyền vào.

Trong controller:

```java
private final PropertyEditorRegistrar editors;

public OrderController(PropertyEditorRegistrar editors) {
    this.editors = editors;
}

@InitBinder("orderForm")
void initBinder(WebDataBinder binder) {
    editors.registerCustomEditors(binder);
    binder.setAllowedFields("createdOn", "delivery.shipOn");
}
```

Đây là snippet thành viên class `@Controller`; phải cấu hình một bean triển khai `PropertyEditorRegistrar` và tiêm vào constructor. **Điều cần giữ:** một registrar có thể được tái sử dụng, nhưng mỗi lần `registerCustomEditors` được gọi nên **tạo editor instance mới** để tránh chia sẻ trạng thái giữa các binder/request. Spring cũng nhấn mạnh điều này trong tài liệu chính thức.

Có thể sử dụng `CustomEditorConfigurer` để tích hợp các registrar/editor vào **IoC BeanFactory** khi cấu hình thuộc tính bean. Đó là phạm vi **bean configuration**, khác với việc đăng ký trên `WebDataBinder` phục vụ request. Đừng cho rằng đăng ký ở container luôn làm mọi `@ModelAttribute` binder và JSON converter tự dùng cùng rule.

## 10. Scope và vòng đời: mỗi editor thuộc về binder nào?

`java.beans.PropertyEditor` là API có trạng thái. Các implementation thường lưu giá trị hiện tại thông qua `setValue(...)` / `getValue()`; nhiều editor còn giữ formatter hoặc cấu hình parse.

Điều này kéo theo các nguyên tắc:

- Tạo editor mới khi xây một `BeanWrapperImpl` hoặc `DataBinder` mới; trong `@InitBinder`, tạo editor per-binder.
- Không giữ một `PropertyEditorSupport` mutable dùng chung trong một singleton controller rồi đưa cho mọi request.
- Không truyền cùng một `SimpleDateFormat` mutable sang nhiều editor ở các request song song.
- Có thể tái sử dụng object `PropertyEditorRegistrar` nếu registrar không giữ mutable editor instance và tạo editor mới mỗi lần đăng ký.
- Không coi custom editor là bean singleton chỉ vì nó chuyển đổi giữa String và một type phổ biến.

Ví dụ **không nên làm**:

```java
// Sai về thiết kế chia sẻ trạng thái khi nhiều request cùng truy cập:
private static final DayMonthYearEditor SHARED_EDITOR =
        new DayMonthYearEditor();

@InitBinder
void init(WebDataBinder binder) {
    binder.registerCustomEditor(
            LocalDate.class, SHARED_EDITOR);
}
```

Đây là anti-pattern minh họa, cần một method/class controller phù hợp. Một editor mới ở mỗi lần đăng ký là cách dễ kiểm soát hơn:

```java
@InitBinder
void init(WebDataBinder binder) {
    binder.registerCustomEditor(
            LocalDate.class, new DayMonthYearEditor());
}
```

Dù `DateTimeFormatter` bản thân immutable và có thể dùng chung, **PropertyEditorSupport** vẫn là object stateful. Do đó việc giữ một `DateTimeFormatter` static final không đồng nghĩa nên giữ một editor static final.

## 11. Editor, Converter và Formatter khác nhau thế nào?

Spring hỗ trợ nhiều tầng chuyển đổi dữ liệu:

| Cơ chế | API chính | Hướng sử dụng |
| --- | --- | --- |
| JavaBeans `PropertyEditor` | `setAsText`, `getAsText`, `setValue` | Legacy/custom binder hoặc quy tắc rất cụ thể |
| Spring `Converter<S,T>` | `T convert(S source)` | Chuyển một kiểu nguồn thành một kiểu đích, thường stateless |
| Spring `Formatter<T>` | `parse(String, Locale)`, `print(T, Locale)` | Parse/format có ngữ cảnh ngôn ngữ/địa phương |
| `ConversionService` | `convert(...)`, `canConvert(...)` | Registry thực hiện conversion dùng lại nhiều nơi |
| `@DateTimeFormat` / `@NumberFormat` | Annotation trên field/parameter | Gợi ý format với formatting infrastructure phù hợp |

**Khi nào vẫn dùng PropertyEditor?** Khi hệ thống đang sử dụng `PropertyEditorRegistry`/`@InitBinder`, có yêu cầu đường dẫn cụ thể, custom editor legacy cần được giữ, hoặc logic parse đặc thù chỉ thuộc một binder.

**Khi nào ưu tiên Formatter/Converter?** Khi xây code mới cần conversion tái sử dụng giữa nhiều tầng, có locale hoặc muốn đăng ký tập trung trong `FormattingConversionService`. Để riêng `delivery.shipOn` dùng format khác mà không viết editor, cũng có thể cân nhắc annotation `@DateTimeFormat` ngay trên property hoặc cơ chế custom formatter theo nhu cầu.

**Không mô tả `PropertyEditor` là một `Converter` có thể chia sẻ an toàn như nhau.** `Converter` thường được viết stateless, trong khi `PropertyEditor` thường giữ mutable value. Tương tự, `PropertyEditor#getAsText()` không tự biến thành serializer JSON của Jackson.

### Khi có ConversionService và custom editor cùng hiện diện

Cơ chế lựa chọn có thể phụ thuộc type, path, converter phù hợp và cấu hình binder. Một custom editor đã đăng ký cho path cụ thể thường là lựa chọn có độ đặc hiệu cao cho property đó. Khi gặp xung đột giữa conversion theo type và path, hãy kiểm tra bằng test đúng version Spring đang chạy, tránh suy luận mơ hồ rằng thứ tự đăng ký luôn quyết định tất cả.

## 12. Lỗi binding và việc kiểm tra FieldError

Editor parse một chuỗi sai có thể phát sinh exception. Trong `BeanWrapperImpl.setPropertyValue(...)` trực tiếp, caller thường nhận exception của Spring Beans/property access. Trong `DataBinder.bind(...)`, những lỗi chuyển kiểu/property thường được ghi thành `FieldError` trong `BindingResult`.

Ví dụ:

```text
createdOn=2026-11-02
delivery.shipOn=31/02/2026
```

Với editor trong ví dụ, `31/02/2026` là ngày không có thật. `LocalDate.parse` không thể tạo `LocalDate`; trong binder cấu hình phù hợp, kết quả có thể là lỗi `typeMismatch` cho `delivery.shipOn`.

Các phương thức hữu ích:

```java
BindingResult result = binder.getBindingResult();

if (result.hasErrors()) {
    result.getFieldErrors().forEach(error -> {
        System.out.println("field=" + error.getField());
        System.out.println("code=" + error.getCode());
        System.out.println(
                "bindingFailure=" + error.isBindingFailure());
    });
}
```

Snippet này cần đặt trong method có biến `binder` kiểu `DataBinder`. Không in `getRejectedValue()` ra log production vì nó có thể chứa input nhạy cảm. Với form web, phản hồi nên chứa tên field và message an toàn theo `MessageSource` hoặc error DTO của API.

**Đổi định dạng không thay validation:** `@NotNull`, `@Past`, `@Future` và constraint nghiệp vụ phải được kiểm tra bởi Bean Validation hoặc Spring Validator. Editor chỉ cố parse và gán giá trị vào property. Một giá trị chuyển kiểu thành công vẫn có thể vi phạm quy tắc nghiệp vụ.

## 13. An toàn khi dùng field-specific editor

Dùng một editor riêng cho field có thể giảm tác động ngoài ý muốn so với đăng ký rộng theo type. Tuy nhiên **editor không phải bộ lọc quyền truy cập** và không tự giới hạn những field mà client được phép gán.

Ví dụ bean có:

```text
OrderForm
├── createdOn
├── delivery.shipOn
├── approved
├── price
└── role
```

Đăng ký editor chỉ cho `delivery.shipOn` **không ngăn** client thử gửi `approved=true` hoặc `role=ADMIN` nếu model có writable property và binder được phép gán. Với input không tin cậy:

1. Dùng request DTO chỉ chứa field mà client được phép gửi.
2. Giới hạn property binding, ví dụ `binder.setAllowedFields("createdOn", "delivery.shipOn")`.
3. Validate cấu trúc dữ liệu và giới hạn độ sâu/index cho nested/collection input.
4. Áp dụng authorization trong service trước khi cập nhật entity thật.
5. Không cho một custom editor thực hiện thao tác ngoại vi tùy ý dựa trên chuỗi request, ví dụ mở file, tải URL hay truy xuất database không kiểm soát.
6. Tránh parse dữ liệu nhạy cảm rồi log raw input hoặc exception có chứa input.

Một editor chỉ nên chuyển dữ liệu; quyết định quyền và trạng thái nghiệp vụ thuộc tầng service/authorization.

## 14. Những lỗi cấu hình thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân hay gặp | Cách kiểm tra |
| --- | --- | --- |
| Editor riêng không chạy | Sai `propertyPath` hoặc đặt tiền tố model name dư | So tên property tương đối với target, ví dụ `delivery.shipOn` |
| Hai trường cùng kiểu bị parse giống nhau | Chỉ có type editor, quên field-specific editor | Đăng ký overload ba tham số |
| Editor chung làm thay đổi field ngoài dự tính | Dùng `String.class` / `Date.class` trên binder có nhiều property | Thu hẹp theo path hoặc dùng annotation/formatter |
| Lỗi với nested path | Bean trung gian `null` hoặc tên property không writable | Khởi tạo object con hoặc cấu hình auto-grow thích hợp |
| CustomDateEditor không áp dụng cho LocalDate | Editor dành cho `java.util.Date` | Viết editor đúng kiểu hoặc dùng Java Time formatter |
| Dùng `items[*].quantity` nhưng không khớp | Nhầm wildcard syntax | Theo ví dụ Javadoc, dùng `items.quantity` và test indexed property |
| Collection element không được parse | Đăng ký editor cho container thay vì element | Kiểm tra `requiredType`/generic type/path |
| Đăng ký hai editor cùng collection path | API chỉ hỗ trợ một custom editor/path | Chọn thiết kế cho collection hoặc cho phần tử |
| Mọi request dùng chung editor | Editor mutable bị reuse | Tạo editor mới trong `@InitBinder`/registrar |
| Ngày sai không sinh validation message như mong muốn | Chỉ có parsing, thiếu message codes/validator | Đọc `BindingResult`, cấu hình messages/validation |
| JSON request không dùng @InitBinder editor | Body được parse bằng HTTP message converter | Dùng Jackson configuration cho JSON |
| Đăng ký sau khi bind xong | Conversion đã diễn ra | Đăng ký editor trước `bind(...)` |
| Setter không tồn tại | Property không writable | Kiểm tra JavaBean getter/setter |
| Chỉ có `getAsText`, không có `setAsText` | Thiếu logic String → value | Implement đúng chiều chuyển đổi cần dùng |
| Editor ném `IllegalArgumentException` với input sai | Định dạng/giá trị không hợp lệ | Dùng binder xử lý lỗi và trả phản hồi rõ ràng |
| Tưởng type editor áp dụng toàn hệ thống | Registry chỉ thuộc binder/wrapper hiện tại | Xác định scope BeanFactory/MVC/binder |

Đối với controller, dùng integration test gửi form thật để xác nhận cơ chế binding theo path, vì việc editor hoạt động khi gọi `BeanWrapperImpl` trực tiếp chưa chứng minh mọi đường `@RequestBody` hay controller sẽ dùng nó.

## 15. Kiểm thử đúng hai phạm vi đăng ký

Một bộ test có giá trị nên bao phủ ít nhất:

| Test | Input | Kết quả mong đợi |
| --- | --- | --- |
| Editor theo kiểu | `createdOn=2026-11-02` | `LocalDate 2026-11-02` |
| Editor theo path | `delivery.shipOn=03/11/2026` | `LocalDate 2026-11-03` |
| Sai kiểu format của path | `delivery.shipOn=2026-11-03` | Bị từ chối bởi DMY editor trong ví dụ |
| Ngày không tồn tại | `delivery.shipOn=31/02/2026` | Lỗi chuyển kiểu |
| Nested object chưa tạo | `delivery=null` | Cần khởi tạo/auto-grow phù hợp |
| Các property cùng kiểu khác | Thêm `cancelledOn=2026-11-04` | Dùng type editor mặc định của registry nếu không có path-specific |
| Collection element | `items[0].quantity=2` | Editor element được chọn theo path/type phù hợp |
| Không leak state | Nhiều binder/request độc lập | Editor instance và kết quả từng binder độc lập |
| Mass assignment | Gửi thêm `approved=true` | Binder/DTO không ghi field không được phép |

### Tự kiểm tra tại điểm đăng ký

`BeanWrapperImpl` và các registry tương ứng còn có cơ chế tra cứu editor:

```java
import java.beans.PropertyEditor;
import java.time.LocalDate;

PropertyEditor forCreated =
        wrapper.findCustomEditor(
                LocalDate.class, "createdOn");

PropertyEditor forDelivery =
        wrapper.findCustomEditor(
                LocalDate.class, "delivery.shipOn");
```

Trong method của ví dụ runnable, `forCreated` và `forDelivery` là hai editor được tìm theo path/type tương ứng. Có thể kiểm tra bằng `instanceof` hoặc chạy thử input có hai định dạng khác nhau. Đây là **snippet** có biến `wrapper` đã được cấu hình; không phải chương trình độc lập.

Chỉ kiểm tra `findCustomEditor` là chưa đủ để xác nhận toàn bộ chuyển đổi thành công: hãy thực hiện `setPropertyValue(...)`/`DataBinder.bind(...)` trên DTO có getter/setter thực tế và đối chiếu target sau cùng.

### Kiểm tra message và locale

Nếu ứng dụng hỗ trợ nhiều locale, test dữ liệu theo định dạng địa phương và bản dịch message lỗi. Dùng `Formatter` nếu parsing thực sự phụ thuộc `Locale` do request quyết định, thay vì dùng một editor singleton cứng một định dạng cho mọi người dùng.

## 16. Checklist áp dụng trong dự án Spring

1. **Xác định target:** tên property và kiểu Java đúng, getter/setter có thể ghi, nested objects được khởi tạo.
2. **Chọn phạm vi:** type nếu mọi property cùng kiểu tuân chung quy tắc; path nếu một property cần quy tắc riêng.
3. **Chọn overload:** `registerCustomEditor(Class, editor)` hoặc `registerCustomEditor(Class, propertyPath, editor)`.
4. **Với collection:** làm rõ editor chuyển cả container hay từng phần tử; đừng đăng ký trùng path.
5. **Đăng ký đúng nơi:** `BeanWrapperImpl` hoặc `DataBinder` trực tiếp; `@InitBinder` cho web form; `PropertyEditorRegistrar` để tái sử dụng.
6. **Tạo editor mới theo binder:** đặc biệt với `PropertyEditorSupport` và `SimpleDateFormat` mutable.
7. **Đăng ký trước khi binding:** đừng chờ tới sau khi field đã được convert.
8. **Kiểm tra lỗi:** `BindingResult` và message codes cho input sai kiểu, sau đó chạy validation riêng nếu có.
9. **Giới hạn field nhận từ client:** DTO và `setAllowedFields(...)` khi dùng property binding.
10. **Kiểm thử cả type và path:** happy path, path-specific override, dữ liệu sai, nested/indexed input, multi-request và security.
11. **Cân nhắc công cụ mới:** `Converter`/`Formatter`/`ConversionService` nếu logic chuyển đổi tái sử dụng rộng hoặc có locale.

## 17. Ghi nhớ cốt lõi

**Đăng ký theo kiểu** có phạm vi rộng trong một registry: `registerCustomEditor(LocalDate.class, editor)` dùng cho các property kiểu ngày tương ứng. **Đăng ký theo đường dẫn** chính xác hơn: `registerCustomEditor(LocalDate.class, "delivery.shipOn", editor)` dành riêng cho ngày giao hàng trong object graph. Khi cần parse nhiều định dạng trên các field cùng kiểu, kết hợp hai phạm vi giúp giữ được quy tắc chung và ngoại lệ có chủ đích.

Editor xử lý chuyển đổi giá trị; scope của binder quyết định nơi đăng ký áp dụng; DTO/allowed fields quyết định field nào được nhận; validator và authorization quyết định dữ liệu nào hợp lệ/được phép. Hiểu rõ các ranh giới này sẽ tránh việc một custom editor ảnh hưởng toàn bộ form hoặc không chạy vì sai property path.

## Tài liệu tham khảo

- [Spring Framework — PropertyEditorRegistry API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/PropertyEditorRegistry.html)
- [Spring Framework — PropertyEditorRegistrySupport API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/PropertyEditorRegistrySupport.html)
- [Spring Framework — Data Binding / PropertyEditors](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring Framework — @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework — DataBinder API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework — BeanWrapperImpl API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/BeanWrapperImpl.html)
- [Spring Framework — PropertyEditorRegistrar API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/PropertyEditorRegistrar.html)
- [Spring Framework — StringTrimmerEditor API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/propertyeditors/StringTrimmerEditor.html)
- [Spring Framework — CustomDateEditor API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/propertyeditors/CustomDateEditor.html)
