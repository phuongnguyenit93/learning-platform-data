# PropertyEditor và PropertyEditorSupport theo chuẩn JavaBeans

Trong JavaBeans, một property có **kiểu dữ liệu thực** (ví dụ `LocalDate`, `URL`, một mã sản phẩm tự định nghĩa) nhưng công cụ cấu hình hoặc giao diện có thể nhận nó dưới dạng **văn bản**. Interface `java.beans.PropertyEditor` là hợp đồng chuẩn JDK để một đối tượng hỗ trợ chỉnh sửa/biểu diễn giá trị property. Lớp `java.beans.PropertyEditorSupport` cung cấp bộ khung triển khai cho hợp đồng ấy.

Spring Framework dùng cơ chế JavaBeans `PropertyEditor` trong **data binding** và cấu hình bean. Khi một chuỗi đi vào property Java, Spring có thể nhờ editor tương ứng parse `String -> Object`; khi cần thể hiện giá trị dạng text, editor có thể hỗ trợ `Object -> String`. Editor không phải Bean, không phải getter/setter của Bean, cũng không phải Validator.

Bài này tập trung vào nguồn gốc JavaBeans, hợp đồng method, cách viết editor bằng `PropertyEditorSupport`, cách đăng ký trong `BeanWrapper`/`DataBinder`/Spring MVC, vòng đời có trạng thái và lựa chọn giữa editor kiểu cũ với `Converter`/`Formatter` hiện đại. Ví dụ chính dùng Java 17+, Maven và Spring Framework 6.2.x.

## 1. Vấn đề mà PropertyEditor giải quyết

Giả sử một form có field `productCode` mang kiểu Java `ProductCode`:

```java
public record ProductCode(String value) {}
```

Đây là kiểu dữ liệu, không phải `String`. Người dùng lại nhập văn bản `"ab-012"`. Trước khi gọi setter `setProductCode(ProductCode)`, ứng dụng cần quy tắc:

1. Bỏ khoảng trắng thừa.
2. Chuẩn hóa chữ cái viết hoa.
3. Kiểm tra cú pháp `AA-999`.
4. Tạo một `ProductCode` mới.
5. Khi cần hiển thị, biến `ProductCode("AB-012")` thành văn bản `"AB-012"`.

```text
                     JavaBeans PropertyEditor

                     setAsText(String)
"ab-012"  --------------------------------->  ProductCode("AB-012")
                     setValue(Object)             |
                                                   |
"AB-012"  <---------------------------------  getValue()
                     getAsText()
```

Với editor có trạng thái, `setAsText(...)` không trả ra đối tượng bằng return value: nó **đặt giá trị bên trong editor** (thường qua `setValue(...)`). Caller đọc lại bằng `getValue()`. Ngược lại, `setValue(...)` cung cấp giá trị có kiểu; `getAsText()` đưa ra cách diễn đạt của giá trị hiện tại.

**Quan trọng:** `PropertyEditor` tự nó không biết property nào được phép sửa hoặc ai có quyền sửa. Đây là **cơ chế chuyển đổi/chỉnh sửa giá trị**, không phải công cụ authorization hay validation nghiệp vụ.

## 2. JavaBeans property khác Java field như thế nào?

Theo convention JavaBeans, property thường được biểu diễn bằng getter/setter:

```java
public final class ProductForm {
    private ProductCode productCode;

    public ProductCode getProductCode() {
        return productCode;
    }

    public void setProductCode(ProductCode productCode) {
        this.productCode = productCode;
    }
}
```

Class trên là ví dụ về mutable JavaBean; `ProductCode` được định nghĩa bên ngoài. Khi Spring `BeanWrapper` xử lý property `productCode`, nó có thể dùng JavaBeans introspection để thấy setter yêu cầu kiểu `ProductCode`. Nếu input lại là `String`, hệ thống có thể gọi editor đã đăng ký để tạo `ProductCode` rồi đưa vào setter.

Ba đối tượng không nên lẫn:

| Thành phần | Trách nhiệm |
| --- | --- |
| `ProductForm` (target bean) | Chứa dữ liệu, cung cấp getter/setter |
| `ProductCode` (value object) | Biểu diễn mã sản phẩm có kiểu |
| `ProductCodeEditor` (property editor) | Chuyển text sang `ProductCode` và ngược lại |

Tên `PropertyEditor` đến từ hạ tầng JavaBeans cho các công cụ chỉnh property, bao gồm những công cụ GUI. Nó **không có nghĩa** mọi editor phải có giao diện đồ họa, và càng không phải editor mã nguồn như IDE.

## 3. Hợp đồng java.beans.PropertyEditor

`PropertyEditor` nằm trong package `java.beans`, thuộc module JDK `java.desktop`. Khi dùng JDK đầy đủ, không cần thêm dependency Spring chỉ để gọi interface chuẩn JavaBeans này.

| Nhóm | API | Ý nghĩa |
| --- | --- | --- |
| Giá trị có kiểu | `setValue(Object)`, `getValue()` | Cập nhật/đọc trạng thái giá trị editor đang chỉnh |
| Chuyển đổi văn bản | `setAsText(String)`, `getAsText()` | Parse text và lấy dạng text |
| Thay đổi trạng thái | `addPropertyChangeListener(...)`, `removePropertyChangeListener(...)` | Đăng ký/hủy listener cho thay đổi giá trị |
| Tùy chọn liệt kê | `getTags()` | Tập các lựa chọn text hữu hạn, nếu có |
| Tùy chọn vẽ | `isPaintable()`, `paintValue(Graphics, Rectangle)` | Dành cho công cụ JavaBeans GUI |
| Tùy chọn giao diện | `supportsCustomEditor()`, `getCustomEditor()` | Trả component GUI tùy chỉnh, nếu hỗ trợ |
| Tạo Java initializer | `getJavaInitializationString()` | Cung cấp biểu thức mã Java biểu diễn giá trị |
 
Interface này rộng hơn yêu cầu Spring MVC. Đa số editor dùng để bind input chỉ cần xử lý đúng `setAsText`, `getAsText` và lưu giá trị qua `setValue`/`getValue`.

Các hợp đồng then chốt:

- `setAsText(String)` có kiểu trả về `void`. Nếu text không có dạng hợp lệ, editor có thể ném `IllegalArgumentException`.
- `getAsText()` trả `String` biểu diễn giá trị hiện tại; có thể trả `null` nếu giá trị không thể biểu diễn dạng text. Nếu trả chuỗi không-null, editor nên có khả năng parse lại chuỗi đó qua `setAsText(...)`.
- `setValue(Object)` và `getValue()` thao tác với giá trị đang được editor giữ, **không đồng nghĩa** trực tiếp ghi hay đọc field của một target bean.
- `getTags()` hữu ích khi chỉ có một số lựa chọn cho property, nhưng không tự làm kiểm tra quyền/validation.
- `getJavaInitializationString()` dùng cho công cụ tạo **mã Java**, không phải cách serialize JSON hay SQL.
- `getCustomEditor()` nói đến `java.awt.Component`. Đó là khả năng tùy chọn trong hệ JavaBeans GUI; không phải component HTML/React/Thymeleaf.

Theo JavaBeans API, một PropertyEditor thường nên có constructor không tham số để công cụ có thể tạo instance. Trong ứng dụng Spring, một số editor cụ thể còn có constructor nhận tùy chọn và được tạo rõ ràng khi đăng ký.

## 4. PropertyEditorSupport giúp ích những gì?

`PropertyEditorSupport`:

```java
public class PropertyEditorSupport implements PropertyEditor {
    // Lớp JDK đã hiện thực các method của interface.
}
```

Đoạn trên là sơ đồ ý tưởng, **không phải toàn bộ mã nguồn JDK**. Lớp thật có hai constructor phổ biến:

```java
new PropertyEditorSupport();
new PropertyEditorSupport(source);
```

Nó giữ trạng thái giá trị, hỗ trợ listener và cung cấp cách triển khai mặc định cho các method khác. Điều này có nghĩa khi muốn viết editor cho một kiểu domain, thường chỉ cần **extends `PropertyEditorSupport` rồi override `setAsText` và `getAsText`**.

Ví dụ cấu trúc:

```java
public final class ProductCodeEditor extends PropertyEditorSupport {
    @Override
    public void setAsText(String text) throws IllegalArgumentException {
        ProductCode parsed = parseProductCode(text);
        setValue(parsed);
    }

    @Override
    public String getAsText() {
        ProductCode current = (ProductCode) getValue();
        return current == null ? "" : current.value();
    }
}
```

Đây là **mã phác thảo**, chưa đầy đủ: hàm `parseProductCode` và class `ProductCode` phải được định nghĩa; bản chạy thật nằm ở phần 6.

`PropertyEditorSupport` **không tự biết** cách parse mọi kiểu domain. Nếu không override `setAsText`, đừng trông chờ class nền tự chuyển được một chuỗi bất kỳ thành `ProductCode`. Điểm lợi của lớp này là không phải tự viết bộ nhớ giá trị và cơ chế listener nếu ứng dụng chỉ cần logic parse/print.

### setValue/getValue của editor không phải setter/getter của Bean

`editor.setValue(productCode)` chỉ thay **trạng thái editor**. Nó không tương đương `form.setProductCode(productCode)`. Spring `BeanWrapper`/`DataBinder` sẽ dùng giá trị sau conversion để gán vào target trong một bước riêng.

```text
setAsText("ab-012")
        |
        v
ProductCodeEditor.setValue(new ProductCode("AB-012"))
        |
        v
ProductCodeEditor.getValue()
        |
        v
BeanWrapper gọi form.setProductCode(ProductCode)
```

Vì vậy, chạy editor trực tiếp là cách rất tốt để unit test quy tắc parse, nhưng **không đủ** để chứng minh editor đã được đăng ký đúng với binder của Spring.

## 5. Parse và print: các quy tắc cần được thiết kế rõ

Một editor text tốt cần có hợp đồng ngữ nghĩa cụ thể:

| Vấn đề | Câu hỏi cần trả lời |
| --- | --- |
| Khoảng trắng | Có chấp nhận `" ab-012 "` không? |
| Chữ hoa/thường | `"ab-012"` có trở thành `"AB-012"` không? |
| Input rỗng | Trả `null` hay báo lỗi? |
| Text không hợp lệ | Ném exception nào? |
| Định dạng đầu ra | Giữ đúng input hay chuẩn hóa một dạng canonical? |
| Tính thuận nghịch | `setAsText(getAsText())` có bảo toàn giá trị ngữ nghĩa? |
| Locale | Quy tắc có phụ thuộc vùng/ngôn ngữ? |
| Dữ liệu nhạy cảm | Có vô tình lộ giá trị qua exception/log/UI không? |

Ví dụ `ProductCode` của bài này có quy tắc:

- Mã đúng dạng **hai chữ cái Latin ASCII**, dấu `-`, **ba chữ số ASCII**.
- `"ab-012"` và `" AB-012 "` được chuẩn hóa về `"AB-012"`.
- `null` hoặc chuỗi toàn khoảng trắng biểu diễn **không có giá trị** (`null`); kiểm tra “bắt buộc nhập” thuộc validator nếu nghiệp vụ yêu cầu.
- `"AB12"` và `"ABC-012"` không hợp lệ và gây `IllegalArgumentException`.
- `getAsText()` cho `null` trả chuỗi rỗng `""`, còn giá trị đã parse trả mã canonical.
- Chuẩn hóa chữ hoa dùng `Locale.ROOT` để không phụ thuộc locale của server.

**Không phải mọi editor cần “biến đầu vào sai thành null”.** Nếu text sai cú pháp nhưng khác rỗng, nên từ chối rõ ràng để hệ thống có thể thông báo lỗi chuyển đổi. Việc yên lặng biến `"???"` thành `null` dễ làm mất dữ liệu và che nguyên nhân thật.

## 6. Ví dụ Java 17+ hoàn chỉnh: PropertyEditorSupport và Spring DataBinder

Ví dụ gồm ba cách sử dụng cùng một editor:

1. Gọi editor JavaBeans **trực tiếp** để thấy cách `setAsText`/`getAsText`/`getValue` hoạt động.
2. Đăng ký editor lên `BeanWrapper` để ghi property có kiểu từ `String`.
3. Đăng ký editor lên `DataBinder` để xem input sai trở thành lỗi binding trong `BindingResult`.

Cấu trúc dự án Maven:

```text
property-editor-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── PropertyEditorDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>property-editor-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/PropertyEditorDemo.java`:

```java
import java.beans.PropertyEditorSupport;
import java.util.Locale;

import org.springframework.beans.BeanWrapper;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.PropertyAccessorFactory;
import org.springframework.beans.propertyeditors.StringTrimmerEditor;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

public class PropertyEditorDemo {

    // Kiểu dữ liệu nội bộ; setter của form nhận ProductCode, không nhận String.
    public record ProductCode(String value) {}

    public static final class ProductCodeEditor extends PropertyEditorSupport {
        @Override
        public void setAsText(String text) throws IllegalArgumentException {
            if (text == null || text.isBlank()) {
                setValue(null);
                return;
            }

            String canonical = text.trim().toUpperCase(Locale.ROOT);
            if (!canonical.matches("[A-Z]{2}-[0-9]{3}")) {
                throw new IllegalArgumentException(
                        "ProductCode must match AA-999");
            }

            setValue(new ProductCode(canonical));
        }

        @Override
        public String getAsText() {
            ProductCode current = (ProductCode) getValue();
            return current == null ? "" : current.value();
        }
    }

    public static class PurchaseForm {
        private ProductCode productCode;
        private String customerName;

        public PurchaseForm() {}

        public ProductCode getProductCode() { return productCode; }
        public void setProductCode(ProductCode code) {
            this.productCode = code;
        }

        public String getCustomerName() { return customerName; }
        public void setCustomerName(String name) {
            this.customerName = name;
        }
    }

    private static void directEditorExample() {
        ProductCodeEditor editor = new ProductCodeEditor();
        editor.setAsText(" ab-012 ");

        ProductCode parsed = (ProductCode) editor.getValue();
        System.out.println("direct.value=" + parsed.value());
        System.out.println("direct.text=" + editor.getAsText());

        editor.setValue(new ProductCode("XY-777"));
        System.out.println("manual.text=" + editor.getAsText());
    }

    private static void beanWrapperExample() {
        PurchaseForm form = new PurchaseForm();

        BeanWrapper wrapper =
                PropertyAccessorFactory.forBeanPropertyAccess(form);
        wrapper.registerCustomEditor(
                ProductCode.class, new ProductCodeEditor());

        // Riêng property customerName: trim khoảng trắng khi ghi.
        wrapper.registerCustomEditor(
                String.class, "customerName",
                new StringTrimmerEditor(false));

        wrapper.setPropertyValue("productCode", "cd-345");
        wrapper.setPropertyValue("customerName", "  Linh  ");

        System.out.println("bean.code=" +
                form.getProductCode().value());
        System.out.println("bean.customer=" +
                form.getCustomerName());
    }

    private static void dataBinderExample() {
        PurchaseForm form = new PurchaseForm();
        DataBinder binder = new DataBinder(form, "purchaseForm");
        binder.registerCustomEditor(
                ProductCode.class, new ProductCodeEditor());

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("productCode", "wrong");
        binder.bind(values);

        BindingResult result = binder.getBindingResult();
        FieldError error = result.getFieldError("productCode");

        System.out.println("bind.errorCount=" + result.getErrorCount());
        System.out.println("bind.field=" +
                (error == null ? "<none>" : error.getField()));
        System.out.println("bind.code=" +
                (error == null ? "<none>" : error.getCode()));
        System.out.println("bind.bindingFailure=" +
                (error != null && error.isBindingFailure()));
    }

    public static void main(String[] args) {
        directEditorExample();
        beanWrapperExample();
        dataBinderExample();
    }
}
```

Chạy từ thư mục `property-editor-demo`, cần JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=PropertyEditorDemo
```

Các dòng do `System.out.println` tạo ra theo logic của ví dụ:

```text
direct.value=AB-012
direct.text=AB-012
manual.text=XY-777
bean.code=CD-345
bean.customer=Linh
bind.errorCount=1
bind.field=productCode
bind.code=typeMismatch
bind.bindingFailure=true
```

**Giải thích:**

1. `editor.setAsText(" ab-012 ")` gọi logic chuẩn hóa rồi `setValue(new ProductCode("AB-012"))`. `getValue()` trả `ProductCode`, còn `getAsText()` trả chuỗi.
2. `editor.setValue(new ProductCode("XY-777"))` thay trực tiếp giá trị có kiểu đang được editor giữ; lần `getAsText()` tiếp theo dựa trên giá trị mới.
3. `BeanWrapper` nhận registration cho `ProductCode.class`. Khi `setPropertyValue("productCode", "cd-345")`, editor giúp chuyển kiểu trước khi gán vào setter của `PurchaseForm`.
4. `StringTrimmerEditor(false)` được đăng ký cho **chỉ** property `customerName`; `"  Linh  "` thành `"Linh"`. Đối số `false` nói rằng chuỗi rỗng sau trim vẫn là chuỗi rỗng, không phải `null`.
5. Case `DataBinder` cung cấp text `"wrong"` không hợp lệ theo mẫu `AA-999`. Editor ném `IllegalArgumentException`; binder trong luồng binding thông thường thu thập lỗi chuyển kiểu thành `FieldError` mã chung `typeMismatch` với `isBindingFailure() == true`.
6. Mã lỗi `typeMismatch` có thể có nhiều mã chi tiết ứng viên trong `error.getCodes()`. Đầu ra chỉ in `getCode()`, tránh phụ thuộc biến thể của message resolver.
7. Ví dụ **không gọi `binder.validate()`**, nên lỗi ở đây thuộc binding, không phải constraint validation.

Chương trình trên hoàn chỉnh theo cấu trúc tệp được nêu. Nếu thay editor, cấu hình message resolver hay dùng phiên bản Spring khác, cần chạy lại để xác nhận đúng behavior và stdout.

## 7. Dùng editor trực tiếp: state, null và round-trip

Editor có thể được tạo mà không có Spring:

```java
ProductCodeEditor editor = new ProductCodeEditor();

editor.setAsText("ab-012");
ProductCode first = (ProductCode) editor.getValue();

editor.setValue(first);
String printed = editor.getAsText();
```

Đoạn này phụ thuộc hai class được định nghĩa ở phần 6, minh họa **hai chiều**: text -> object và object -> text. Nó là nơi tốt nhất để kiểm tra từng quy tắc nhỏ trước khi gắn vào Spring.

### Quy tắc round-trip

Khi editor hỗ trợ text, hãy kiểm tra:

```text
parse(" ab-012 ") = ProductCode("AB-012")
print(ProductCode("AB-012")) = "AB-012"
parse(print(ProductCode("AB-012"))) = ProductCode("AB-012")
```

Dòng cuối so sánh theo **giá trị ngữ nghĩa**, không bắt buộc byte text đầu vào giữ nguyên. Việc chuẩn hóa chữ hoa là thay đổi có chủ đích; nếu UI cần giữ đúng cách nhập ban đầu, phải thiết kế mô hình riêng.

### Null và input trống

Trong ví dụ, `null`/blank qua `setAsText` được biểu diễn bằng `null`. Điều này không có nghĩa property được phép bỏ trống theo nghiệp vụ. Nếu `productCode` là bắt buộc, sử dụng validator thích hợp, chẳng hạn `@NotNull` trong Jakarta Bean Validation, sau khi binding.

Nếu input có ký tự sai hoặc sai độ dài, editor ném `IllegalArgumentException`. Đừng chỉ `catch` rồi `setValue(null)` cho mọi lỗi; cách đó có thể khiến một mã nhập sai bị hiểu nhầm là người dùng không nhập gì.

### Lưu ý về setValue(Object)

`setValue` nhận `Object` theo hợp đồng interface. Nếu caller tùy tiện gọi:

```java
editor.setValue("raw string");
```

mà `getAsText()` của custom editor ép kiểu sang `ProductCode`, có thể xảy ra `ClassCastException`. Mã ở trên là **điều cần tránh**, không phải thao tác hợp lệ trong demo. JavaBeans editor phải được caller dùng đúng loại giá trị; custom editor có thể override `setValue` để kiểm tra type sớm khi thiết kế yêu cầu. Spring thường chọn editor theo kiểu property nhưng code tự gọi editor vẫn cần tuân hợp đồng.

## 8. Đăng ký editor trong Spring: phạm vi phải chính xác

Spring triển khai interface `org.springframework.beans.PropertyEditorRegistry` trong các thành phần như `BeanWrapper` và `DataBinder`. Có hai dạng đăng ký quan trọng:

```java
registry.registerCustomEditor(
        ProductCode.class, new ProductCodeEditor());

registry.registerCustomEditor(
        String.class, "customerName",
        new StringTrimmerEditor(true));
```

Đây là đoạn minh họa với `registry` thuộc kiểu `PropertyEditorRegistry`, và các editor/type đã có.

| Cách đăng ký | Phạm vi | Khi nào chọn |
| --- | --- | --- |
| `registerCustomEditor(ProductCode.class, editor)` | Các property kiểu `ProductCode` trong registry/binder đó | Cùng một quy tắc cho kiểu domain |
| `registerCustomEditor(String.class, "customerName", editor)` | Property path cụ thể trong registry/binder đó | Chỉ trim/format một field |
| `registerCustomEditor(null, "somePath", editor)` | Định vị theo property path | Chỉ dùng khi hiểu rõ type resolution; với collection nên chỉ rõ type |
| `PropertyEditorRegistrar` | Một nơi đăng ký nhiều editor vào registry được truyền | Cần tái sử dụng cấu hình ở nhiều binder/bean |

Không nên đăng ký editor áp dụng mọi `String` nếu chỉ một field cần xử lý. Một `StringTrimmerEditor(true)` đăng ký toàn cục có thể biến các chuỗi chỉ chứa whitespace thành `null` ở mọi field nằm trong phạm vi đó; đó có thể là hành vi đúng cho một số form nhưng bất ngờ ở những field khác.

### Đăng ký theo property path lồng nhau

Spring hỗ trợ đường dẫn như `customer.address.zip`. Với collection, `registerCustomEditor(requiredType, propertyPath, editor)` có logic đối sánh property path riêng; đừng nhầm syntax đăng ký với syntax truy cập phần tử cụ thể.

Ví dụ tài liệu `PropertyEditorRegistry` mô tả đăng ký editor cho phần tử `items[n].quantity` bằng path dạng `items.quantity`, dùng type phù hợp để làm rõ editor áp dụng cho phần tử hay toàn collection. Khi phạm vi này quan trọng, hãy kiểm thử trên cả item index 0 và index lớn hơn 0 trong dự án thật.

Đối với collection/array, cần phân biệt editor dành cho **bản thân list/array** với editor dành cho **từng phần tử**. Chỉ định type chính xác và tránh đăng ký các editor chồng chéo trên cùng path khiến kết quả khó hiểu.

## 9. Tích hợp với BeanWrapper

`BeanWrapper` là lớp làm việc ở mức property của JavaBean:

```java
PurchaseForm form = new PurchaseForm();

BeanWrapper wrapper =
        PropertyAccessorFactory.forBeanPropertyAccess(form);
wrapper.registerCustomEditor(
        ProductCode.class, new ProductCodeEditor());

wrapper.setPropertyValue("productCode", "ab-012");
ProductCode code =
        (ProductCode) wrapper.getPropertyValue("productCode");
```

Đây là đoạn dùng class `PurchaseForm` và `ProductCodeEditor` của phần 6. `getPropertyValue` trả **giá trị có kiểu**, tức `ProductCode`, chứ không mặc định gọi `getAsText` để tạo chuỗi.

Bản chất của hai việc:

- **Đặt giá trị từ text:** `setPropertyValue` tìm kiểu property, dùng editor/conversion thích hợp và gọi setter.
- **Đọc giá trị đã có:** `getPropertyValue` trả giá trị property; nếu muốn text cho UI, dùng editor hoặc formatter thích hợp trong một bước riêng.

### BeanWrapper không tự validate mọi ràng buộc

Editor chỉ xác nhận rằng input có dạng chuyển được sang `ProductCode`. Kiểm tra mã đó có tồn tại trong catalog, người dùng có quyền mua hay không, hoặc số lượng trong kho có đủ không là **validation/logic nghiệp vụ** riêng.

Vì vậy, một editor có thể trả đúng `ProductCode("AB-012")` nhưng đơn hàng vẫn không hợp lệ.

## 10. Tích hợp với DataBinder và BindingResult

`DataBinder` làm việc trên target với tập `PropertyValues`; nó có thể biến lỗi chuyển đổi thành dữ liệu lỗi trong `BindingResult` thay vì buộc tầng giao diện tự giải mã mọi exception.

```java
PurchaseForm form = new PurchaseForm();
DataBinder binder = new DataBinder(form, "purchaseForm");

binder.registerCustomEditor(
        ProductCode.class, new ProductCodeEditor());

MutablePropertyValues input = new MutablePropertyValues();
input.add("productCode", "bad");

binder.bind(input);

BindingResult result = binder.getBindingResult();
if (result.hasFieldErrors("productCode")) {
    // Lấy FieldError, mã typeMismatch và báo người dùng sửa cú pháp.
}
```

Đoạn này cũng phụ thuộc class từ phần 6. Nó **không yêu cầu** gọi `binder.validate()` để có lỗi chuyển kiểu; validation là một giai đoạn khác nếu bạn cấu hình validator.

Phân biệt:

| Tình huống | Cơ chế | Dấu hiệu |
| --- | --- | --- |
| `"ab-012"` parse được | Editor tạo `ProductCode` | Setter nhận đối tượng |
| `"wrong"` parse thất bại | Editor ném `IllegalArgumentException`; binder bắt lỗi binding thông thường | `FieldError`/`typeMismatch` |
| `""` được editor chuyển thành `null` | Kết quả conversion cho “không có giá trị” | Chưa chắc `hasErrors()` |
| `null` vi phạm `@NotNull` | Validator/Bean Validation sau binding | Lỗi constraint khi validation chạy |
| `ProductCode("AB-012")` không tồn tại trong DB | Rule nghiệp vụ | Lỗi service/validator riêng |
| Client gửi tên field ngoài allowlist | Chính sách binding | Có thể ở `getSuppressedFields()`, không mặc nhiên là `FieldError` |

**Ghi chú:** tại API `BeanWrapper.setPropertyValue(...)` trực tiếp, lỗi conversion thường thể hiện bằng exception truy cập/chuyển kiểu; `BindingResult` thuộc `DataBinder` chứ không phải return value của `PropertyEditor.setAsText`.

Nếu dữ liệu chứa bí mật, không log trực tiếp `FieldError.getRejectedValue()`. Nó có thể giữ nguyên input từ client.

## 11. Sử dụng trong Spring MVC qua @InitBinder

Trong Spring MVC xử lý `@ModelAttribute`, có thể tạo editor **mới cho mỗi binder**:

```java
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

@InitBinder("purchaseForm")
void initPurchaseBinder(WebDataBinder binder) {
    binder.registerCustomEditor(
            ProductCode.class, new ProductCodeEditor());

    binder.registerCustomEditor(
            String.class, "customerName",
            new StringTrimmerEditor(true));
}
```

Đây là **một method bên trong controller hoặc controller advice có phạm vi thích hợp**, chưa phải class Spring MVC hoàn chỉnh. Cần import `ProductCode`, `ProductCodeEditor` và `StringTrimmerEditor` từ mã ứng dụng.

Một controller minh họa:

```java
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

@Controller
class PurchaseController {

    @InitBinder("purchaseForm")
    void initBinder(WebDataBinder binder) {
        binder.registerCustomEditor(
                ProductCode.class, new ProductCodeEditor());
    }

    @PostMapping("/purchases")
    String submit(
            @ModelAttribute("purchaseForm") PurchaseForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "purchase-form";
        }

        // Xử lý nghiệp vụ sau khi input đã được kiểm tra đầy đủ.
        return "purchase-success";
    }
}
```

Đây là **đoạn tích hợp minh họa**, cần đầy đủ import `WebDataBinder`/`InitBinder`, các class domain, Spring MVC, view resolver và logic ứng dụng. Không phải file standalone; các tên view chỉ là ví dụ.

**Lưu ý quan trọng:** `BindingResult` nên đứng ngay sau tham số `@ModelAttribute` tương ứng. `@InitBinder` tạo registration cho flow binder cụ thể; custom editor không tự áp dụng cho mọi controller khác.

### @RequestBody JSON không dùng cùng con đường mặc định

Với controller nhận JSON bằng `@RequestBody`, HTTP message converter (thường là Jackson) đọc JSON và tạo object. `@InitBinder`/`PropertyEditor` của form binding **không tự thay serializer/deserializer JSON**.

Nếu API JSON cần `ProductCode` từ chuỗi, thiết kế JSON mapping riêng (ví dụ Jackson deserializer hoặc constructor/creator phù hợp). Đừng kỳ vọng chỉ đăng ký editor đã thay đổi format JSON phản hồi qua `@ResponseBody`.

## 12. PropertyEditorRegistrar: gói cấu hình, tạo editor mới

Khi nhiều binder cần cùng tập editor, interface `org.springframework.beans.PropertyEditorRegistrar` cho phép tập trung công việc đăng ký:

```java
import org.springframework.beans.PropertyEditorRegistrar;
import org.springframework.beans.PropertyEditorRegistry;

public final class PurchaseEditorRegistrar
        implements PropertyEditorRegistrar {

    @Override
    public void registerCustomEditors(PropertyEditorRegistry registry) {
        registry.registerCustomEditor(
                ProductCode.class, new ProductCodeEditor());
        registry.registerCustomEditor(
                String.class, "customerName",
                new StringTrimmerEditor(true));
    }
}
```

Đây là class dùng chung; các class/kiểu trong dự án phải được import. Sử dụng registrar với `BeanWrapper`:

```java
PurchaseEditorRegistrar registrar = new PurchaseEditorRegistrar();

BeanWrapper wrapper =
        PropertyAccessorFactory.forBeanPropertyAccess(new PurchaseForm());

registrar.registerCustomEditors(wrapper);
```

Sử dụng registrar với `DataBinder`:

```java
DataBinder binder =
        new DataBinder(new PurchaseForm(), "purchaseForm");

registrar.registerCustomEditors(binder);
```

**Vì sao registrar quan trọng?** `PropertyEditorSupport` giữ giá trị đang chỉnh; một editor có thể được dùng tuần tự cho nhiều property và trạng thái của nó biến đổi mỗi lần. Khi registrar được gọi cho một registry, hãy **tạo editor instance mới bên trong** như code, không tạo một `static final ProductCodeEditor` rồi chia sẻ giữa các binder/request.

Registrar có thể là singleton nếu bản thân nó không giữ trạng thái mutable của editor. Mỗi lần `registerCustomEditors`, nó vẫn tạo editor riêng cho registry mới.

### CustomEditorConfigurer trong Spring IoC

Nếu bài toán là **chuyển property khi Spring container tạo bean**, không phải form HTTP, Spring cung cấp `CustomEditorConfigurer` để cấu hình editor/registrar cho `ApplicationContext` hoặc `BeanFactory`.

Ví dụ XML mang tính cấu hình:

```xml
<bean id="purchaseEditorRegistrar"
      class="example.PurchaseEditorRegistrar"/>

<bean class="org.springframework.beans.factory.config.CustomEditorConfigurer">
    <property name="propertyEditorRegistrars">
        <list>
            <ref bean="purchaseEditorRegistrar"/>
        </list>
    </property>
</bean>
```

Đây là **trích đoạn Spring XML**, cần các namespace/root document và class path thực tế. Phải phân biệt hai phạm vi:

- **Container bean property conversion:** khi khởi tạo/cấu hình bean trong IoC container.
- **Web MVC form binding:** khi bind request vào model attribute.

Đăng ký editor qua `CustomEditorConfigurer` cho bean factory **không phải cách bảo đảm** MVC controller sẽ dùng editor đó. Nếu nhu cầu ở form, hãy đăng ký vào đúng `WebDataBinder` hoặc dùng config MVC phù hợp.

## 13. Lifecycle, trạng thái và an toàn đa luồng

Khác một converter hàm thuần, `PropertyEditorSupport` có **state mutable**: `setValue` thay giá trị đang được editor giữ; `getValue` đọc trạng thái đó. Nếu một editor instance được dùng đồng thời cho các request khác nhau, có nguy cơ:

```text
Request A: editor.setAsText("AB-001")
Request B: editor.setAsText("CD-002")
Request A: editor.getValue()  -> có thể thấy "CD-002"
```

Đây là minh họa race condition, không phải chương trình Java độc lập. Vì thế:

1. Không đặt một `ProductCodeEditor` mutable làm singleton dùng chung cho nhiều request.
2. Với `@InitBinder`, tạo `new ProductCodeEditor()` cho binder của request.
3. Với `PropertyEditorRegistrar`, tạo instance editor mới trong mỗi lần đăng ký.
4. Nếu cần logic parse dùng chung, đặt nó trong utility/service **stateless**; editor mới có thể gọi utility đó.
5. Không lưu tham chiếu tới state của editor trong component khác nếu không quản lý vòng đời rõ.
6. Test đồng thời nên tập trung vào tính bất biến của dữ liệu/domain và việc mỗi binder có editor riêng.

Spring documentation nhấn mạnh registrar tạo editor mới cho mỗi lượt bean creation/binding nhằm tránh đồng bộ hóa editor dùng chung. Việc tạo object nhỏ thường rẻ hơn lỗi race condition khó tái hiện.

### PropertyChangeListener và sự kiện

`PropertyEditor` có cơ chế `addPropertyChangeListener`; `PropertyEditorSupport` cung cấp lưu trữ listener và `firePropertyChange()`. Đây là khả năng hỗ trợ các công cụ quan sát thay đổi giá trị, đặc biệt trong thế giới JavaBeans GUI.

```java
import java.beans.PropertyChangeListener;

ProductCodeEditor editor = new ProductCodeEditor();
PropertyChangeListener listener = event -> {
    // Một giá trị đang được editor chỉnh đã thay đổi.
};
editor.addPropertyChangeListener(listener);
editor.setAsText("ab-012");
editor.removePropertyChangeListener(listener);
```

Đây là đoạn minh họa sử dụng editor từ phần 6. Không nên triển khai API HTTP request bằng cách gắn listener lâu dài vào editor singleton. Sự kiện property change của editor **khác** Spring application event, entity/domain event và transaction event.

Constructor `PropertyEditorSupport(Object source)` chỉ định nguồn của event; đối tượng source này không phải target mà editor được phép tự ý sửa. `getSource()` giúp biết nguồn phát sự kiện, không thay cách `DataBinder` gán property.

## 14. Các phương thức GUI ít dùng trong web

Do xuất thân từ JavaBeans, `PropertyEditor` có một số method liên quan công cụ chỉnh property bằng GUI:

| Phương thức | Khi nào có giá trị | Không nên hiểu là |
| --- | --- | --- |
| `getTags()` | Một tập giá trị có thể chọn, tương tự lựa chọn text hữu hạn | Spring MVC HTML select sẽ tự động tạo ra nó |
| `isPaintable()/paintValue(...)` | Công cụ JavaBeans GUI muốn tự vẽ giá trị | Render HTML/canvas frontend |
| `supportsCustomEditor()/getCustomEditor()` | Công cụ desktop muốn một AWT component tùy chỉnh | React/Thymeleaf component |
| `getJavaInitializationString()` | Công cụ sinh mã Java để tạo lại giá trị | JSON string, SQL hoặc text nhập của người dùng |

Một editor dùng cho Spring server-side binding có thể không dùng các khả năng GUI này. Không nhất thiết override tất cả chỉ để parse một `String`. Khi muốn xây dropdown HTML, khai báo lựa chọn ở tầng view/model phù hợp và kiểm tra value trên server; `getTags()` không thay authorization hay validation.

### Ví dụ getTags đơn giản

```java
@Override
public String[] getTags() {
    return new String[] {"NEW", "ACTIVE", "DISABLED"};
}
```

Đây là **method có thể đặt trong một custom editor cho trạng thái**, không thuộc `ProductCodeEditor` ở phần 6. Nếu dùng danh sách tag, `setAsText` cần nhận đúng các tag tương ứng, và `getAsText` nên biểu diễn trạng thái hiện tại bằng một trong những tag đó.

## 15. Một số PropertyEditor có sẵn của Spring

Spring có các implementation trong package `org.springframework.beans.propertyeditors`. Những ví dụ đáng biết:

| Editor | Mục đích | Ghi chú |
| --- | --- | --- |
| `StringTrimmerEditor` | Trim chuỗi; tùy chọn biến rỗng thành `null` | Thường phải **tự đăng ký** |
| `CustomDateEditor` | Chuyển chuỗi với `java.text.DateFormat` thành `Date` | Dùng đúng format/leniency, quản lý instance không an toàn đa luồng |
| `CustomNumberEditor` | Chuyển chuỗi thành kiểu `Number` phù hợp | Kiểm soát số rỗng, kiểu số và định dạng |
| `ClassEditor` | Chuyển tên class thành `Class` | Thuộc nhóm hỗ trợ cấu hình |
| `URLEditor` | Chuyển chuỗi thành `URL` | Không tự xác nhận URL an toàn để kết nối mạng |
| `ByteArrayPropertyEditor` | Chuyển chuỗi thành byte array theo quy tắc editor | Không mặc định giải mã mọi encoding tùy ý |

**Không phải editor nào cũng được đăng ký mặc định cho mọi binder/container**. Ví dụ, Spring tài liệu nhấn mạnh `StringTrimmerEditor` không được đăng ký mặc định; cần cấu hình chủ động.

Đặc biệt, `CustomDateEditor` thường sử dụng `DateFormat` có trạng thái mutable. Nếu nhiều luồng dùng chung một instance `SimpleDateFormat`, kết quả có thể không ổn định. Với mã mới dùng `java.time`, thường nên cân nhắc `Formatter`/`ConversionService` và các kiểu ngày hiện đại thay vì giữ editor cũ nếu không có lý do tương thích.

### Ví dụ trim chuỗi trong MVC

```java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.registerCustomEditor(
            String.class, new StringTrimmerEditor(true));
}
```

Đây là method MVC, cần imports `WebDataBinder`, `InitBinder` và `StringTrimmerEditor`. Khi đăng ký theo **toàn bộ kiểu `String`** trong binder này, mọi property `String` mà editor áp dụng có thể bị trim, và text rỗng trở thành `null`. Trước khi áp dụng toàn form, cần chắc contract của từng field có chấp nhận sự biến đổi đó.

## 16. PropertyEditor so với Converter và Formatter

Spring hiện đại có hai abstraction liên quan:

- `Converter<S,T>` trong `org.springframework.core.convert.converter`: chuyển kiểu theo hướng xác định, ví dụ `String -> ProductCode`, không giữ state như `PropertyEditorSupport` và không nhận `Locale` qua method convert.
- `Formatter<T>` trong `org.springframework.format`: triển khai `Parser<T>` và `Printer<T>`, hỗ trợ `Locale` cho nhập/hiển thị văn bản.
- `ConversionService`/`FormattingConversionService`: cơ sở đăng ký và thực thi converter/formatter; tích hợp với binder/framework nếu cấu hình đúng.

So sánh:

| Khía cạnh | PropertyEditor / PropertyEditorSupport | Converter | Formatter |
| --- | --- | --- | --- |
| Nguồn gốc | JavaBeans trong JDK | Spring Core | Spring Format |
| Hướng thông dụng | Text <-> Object thông qua state | Kiểu S -> T | Text <-> T |
| Nhận Locale trực tiếp? | `setAsText` không nhận Locale | `convert` không nhận Locale | `parse/print` có Locale |
| Trạng thái mutable | Có trong `PropertyEditorSupport` | Thường stateless | Thường stateless |
| Cấu hình | `registerCustomEditor` | `ConverterRegistry` | `FormatterRegistry` |
| Điểm mạnh | Legacy JavaBeans/Ioc và binder hiện có | Chuyển kiểu tổng quát | Ngày, số, UI i18n |
| Lưu ý | Không chia sẻ editor instance; vòng đời | Conversion không mặc định validation | Locale/pattern phải nhất quán |

**Khi nào chọn editor?**

- Dự án có hệ JavaBeans `PropertyEditor`/Spring `DataBinder` sẵn.
- Cần đăng ký riêng cho một property path với semantics kiểu editor.
- Tương thích legacy framework hoặc custom editor đã được kiểm chứng.

**Khi nào chọn converter/formatter cho mã mới?**

- Cần chuyển kiểu dùng chung ở nhiều nơi và không cần trạng thái editor.
- Cần định dạng dựa trên locale, như số tiền và ngày, qua `Formatter`.
- Muốn áp dụng tập trung qua `ConversionService`/`FormattingConversionService`.

Không có lý do để **viết lại hàng loạt editor đang chạy ổn** chỉ vì tồn tại API mới. Tuy nhiên, khi thiết kế module mới, lựa chọn stateless thường dễ test, kiểm soát concurrency và chia sẻ hơn.

### Chuyển editor thành converter: ví dụ so sánh

```java
import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

public final class ProductCodeConverter
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        if (source == null || source.isBlank()) {
            return null;
        }
        String code = source.trim().toUpperCase(Locale.ROOT);
        if (!code.matches("[A-Z]{2}-[0-9]{3}")) {
            throw new IllegalArgumentException(
                    "ProductCode must match AA-999");
        }
        return new ProductCode(code);
    }
}
```

Đây là class minh họa, cần import `ProductCode` trong project. Nó thực hiện **một chiều** `String -> ProductCode`. Nếu ứng dụng cần thêm `ProductCode -> String`, có thể đăng ký converter đảo chiều hoặc dùng `Formatter<ProductCode>` cho UI. Một editor duy nhất vốn có thể thể hiện cả hai chiều bằng `setAsText/getAsText`.

## 17. Validation và bảo mật: editor không quyết định tất cả

Ngay cả khi editor parse được `"AB-012"` thành `ProductCode`, vẫn còn các câu hỏi nghiệp vụ:

- Code này có tồn tại trong danh mục không?
- Mã có thuộc tenant/tài khoản mà người dùng được phép thao tác không?
- Người dùng có được gán field `productCode` hay không?
- Có quota/tần suất/giới hạn kích thước input không?
- Thông báo lỗi có để lộ dữ liệu nhạy cảm không?

Các kiểm tra trên thuộc validation, authorization, request limits và service/domain. Không đưa truy vấn database đắt tiền hoặc hành vi ghi dữ liệu vào `setAsText` một cách mặc định: editor có thể được gọi trong các tình huống bind/convert ngoài dự tính, dễ làm hiệu ứng phụ khó kiểm soát.

### Chống mass assignment

Một request có thể chứa tên property ngoài contract. Dù có editor hợp lệ cho một kiểu, việc người dùng được sửa field đó phải được xét riêng. Với Spring `DataBinder`:

```java
DataBinder binder = new DataBinder(form, "purchaseForm");

binder.setAllowedFields("productCode", "customerName");
binder.registerCustomEditor(
        ProductCode.class, new ProductCodeEditor());
```

Đây là đoạn đặt trong code có biến `form` kiểu `PurchaseForm`. `setAllowedFields` hạn chế các property được phép bind trong nhánh property binding; editor chỉ xử lý conversion khi field được phép.

Nếu request mang field bị loại, xem `binder.getBindingResult().getSuppressedFields()`. Các field bị suppressed **không nhất thiết** được đếm trong `hasErrors()`, nên nếu API yêu cầu strict input schema cần kiểm tra chúng riêng.

### Giới hạn đầu vào

Một editor parse chuỗi không kiểm soát số parameter, độ sâu property path hay kích thước HTTP body. Những ràng buộc đó phải được áp dụng ở tầng HTTP/binding tương ứng. Nếu chỉ cần mã `AA-999`, logic regex cố định như ví dụ vừa rõ vừa tránh xử lý dữ liệu quá phức tạp; vẫn nên giới hạn kích thước request ở tầng trước.

### Lỗi không nên phản hồi nguyên văn exception

Trong ví dụ, exception có thông điệp kỹ thuật `ProductCode must match AA-999`. Với UI thực, nên map mã lỗi `typeMismatch` cùng context field sang thông điệp thân thiện như “Mã sản phẩm phải có dạng AB-123”, thông qua `MessageSource` hoặc cơ chế response lỗi của ứng dụng.

Đặc biệt không trả stack trace hoặc toàn bộ rejected value nhạy cảm cho client.

## 18. Test editor tách biệt và test qua binder

Nên tách test thành hai cấp:

### Cấp 1: unit test của editor

Với `ProductCodeEditor`, kiểm tra:

| Input/hành động | Kỳ vọng |
| --- | --- |
| `setAsText("ab-012")` | `getValue()` là `ProductCode("AB-012")` |
| `setAsText(" AB-012 ")` | Giá trị tương đương `"AB-012"` |
| `setAsText("")` | `getValue() == null` |
| `setAsText("   ")` | `getValue() == null` |
| `setAsText("ABC-012")` | `IllegalArgumentException` |
| `setAsText("AB12")` | `IllegalArgumentException` |
| `setValue(new ProductCode("XY-777"))` | `getAsText()` là `"XY-777"` |
| `setAsText(getAsText())` trên giá trị hợp lệ | Bảo toàn giá trị ngữ nghĩa |

Nếu dùng JUnit Jupiter:

```java
ProductCodeEditor editor = new ProductCodeEditor();

editor.setAsText("ab-012");
org.junit.jupiter.api.Assertions.assertEquals(
        new ProductCode("AB-012"), editor.getValue());

org.junit.jupiter.api.Assertions.assertEquals(
        "AB-012", editor.getAsText());

org.junit.jupiter.api.Assertions.assertThrows(
        IllegalArgumentException.class,
        () -> editor.setAsText("invalid"));
```

Đây là **trích đoạn JUnit**, cần dependency JUnit Jupiter và các class từ phần 6. Chưa phải test class hoàn chỉnh.

### Cấp 2: integration test với BeanWrapper/DataBinder

Cần xác minh:

1. Có `registerCustomEditor(...)` đúng kiểu `ProductCode` không?
2. Với `BeanWrapper.setPropertyValue("productCode", "ab-012")`, target nhận object đúng kiểu không?
3. Với `DataBinder.bind(...)` và input sai, `BindingResult` có đúng field/mã lỗi không?
4. Nếu có editor chỉ áp dụng cho field `customerName`, field String khác có bị ảnh hưởng không?
5. Nếu có validator sau binding, lỗi parse và lỗi nghiệp vụ có được phân biệt không?
6. Nếu binder được tạo cho nhiều request, editor instance có bị chia sẻ bất ngờ không?
7. Với input `null`/rỗng, validation `@NotNull` có chạy theo ý định không?
8. Với input ngoài `allowedFields`, `getSuppressedFields()` có được xử lý không?

Test parse trực tiếp PASS **không chứng minh** Spring đã đăng ký editor. Ngược lại, test chỉ số lỗi của binder không giúp xác định regex canonicalization có đúng mọi trường hợp. Cần cả hai.

### Test i18n khi sử dụng định dạng

Editor trong ví dụ dùng `Locale.ROOT` nên output nhất quán giữa máy dev và CI. Với số/ngày phụ thuộc locale, không dùng `Locale.getDefault()` ngầm trong code rồi dựa vào output một máy. Chọn hợp đồng rõ ràng; nếu cần formatting theo từng request, `Formatter<T>` nhận `Locale` trực tiếp thường thích hợp hơn.

## 19. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Hướng khắc phục |
| --- | --- | --- |
| `setAsText("AB-012")` không đổi giá trị | Quên `setValue(...)` trong override | Gọi `setValue(parsed)` sau khi parse |
| `getAsText()` trả dữ liệu lạ | Không override hoặc cast type sai | Override rõ cách in từ `getValue()` |
| Editor chạy trực tiếp nhưng không chạy khi submit | Chưa đăng ký vào đúng `WebDataBinder` | Dùng `@InitBinder` đúng model |
| BeanWrapper vẫn báo `TypeMismatchException` | Type/path đăng ký không khớp | Kiểm tra `registerCustomEditor` và property type |
| Form có lỗi `typeMismatch` | Text không parse được | Kiểm tra parser, thông báo, rejected value an toàn |
| Input rỗng không báo lỗi | Editor biến rỗng thành `null` nhưng chưa có validator | Dùng `@NotNull` hoặc validator khi cần |
| Cùng editor bị lẫn giá trị giữa request | Dùng singleton mutable editor | Tạo editor mới theo registry/binder |
| Trim một field làm thay đổi các field khác | Editor đăng ký theo toàn `String.class` | Đăng ký theo property path nếu cần |
| Editor không áp dụng với `@RequestBody` | JSON dùng message converter | Cấu hình JSON mapping riêng |
| Lỗi bị nuốt, target trở thành `null` | Parser coi mọi input sai là empty | Chỉ trả null cho trạng thái đã quy định |
| Hiển thị sai locale | PropertyEditor không có tham số locale | Xem xét `Formatter` và context locale |
| Lỗi logic bị đẩy vào editor | Editor làm quá nhiều việc ngoài conversion | Giữ editor thuần conversion, validate riêng |
| CustomEditorConfigurer không ảnh hưởng MVC | Đăng ký ở bean factory, không ở MVC binder | Cấu hình vào đúng nơi sử dụng |
| API log nguyên BindingResult | Có thể lộ `rejectedValue` | Chỉ log field/code đã lọc |

### Checklist gỡ lỗi nhanh

1. Xác định đúng luồng: Spring IoC bean creation, `BeanWrapper`, `@ModelAttribute` hay `@RequestBody`.
2. Kiểm tra **kiểu property thật** và path; ví dụ setter nhận `ProductCode` hay `String`?
3. Chạy `editor.setAsText(text)` trực tiếp với input gây lỗi; xác nhận `getValue()`.
4. Đặt điểm kiểm tra ở `registerCustomEditor`: registration có xảy ra cho đúng registry không?
5. Kiểm tra editor có được tạo mới cho mỗi binder/registry không.
6. Kiểm tra `BindingResult.getFieldError("productCode")` và `getCodes()`.
7. Phân biệt `hasErrors()` với `getSuppressedFields()`.
8. Chỉ sau conversion mới đánh giá rule nghiệp vụ như tính tồn tại của mã.
9. Kiểm tra UI lấy message qua resolver phù hợp, không in exception trực tiếp.

## 20. Câu hỏi tự kiểm tra

**1. `PropertyEditor` và `PropertyEditorSupport` có phải các class Spring không?**  
Không. Chúng thuộc `java.beans` của JDK. Spring tích hợp chúng để chuyển property value trong IoC/binding.

**2. `setAsText(String)` trả về kiểu gì?**  
`void`. Nó phải cập nhật trạng thái editor (thường bằng `setValue(...)`); caller đọc lại object bằng `getValue()`.

**3. Vì sao `PropertyEditorSupport` giúp viết editor ngắn hơn?**  
Nó đã cung cấp lưu trữ giá trị, quản lý listener và implementation mặc định của interface. Thông thường chỉ cần override logic parse/print cần thiết.

**4. Khi gọi `editor.setValue(new ProductCode(...))`, target JavaBean có tự được thay đổi không?**  
Không. Lệnh chỉ thay trạng thái editor; `BeanWrapper`/`DataBinder` là thành phần đưa giá trị vào setter của target.

**5. Một `@InitBinder` được khai báo nhưng controller nhận `@RequestBody` JSON; editor có chắc chạy không?**  
Không. JSON thường được xử lý qua HTTP message converter, cần cấu hình deserialization riêng nếu cần.

**6. Tại sao không nên dùng một PropertyEditorSupport singleton cho mọi request?**  
Vì editor giữ mutable state. Dùng chung có thể gây race condition và lẫn giá trị giữa request. Tạo instance mới theo registry/binder.

**7. `StringTrimmerEditor(true)` và `StringTrimmerEditor(false)` khác nhau ở đâu?**  
Sau trim, `true` biến chuỗi rỗng thành `null`; `false` giữ chuỗi rỗng. Cả hai cần đăng ký ở phạm vi phù hợp.

**8. `getAsText()` có đảm bảo JSON response sẽ dùng cùng format không?**  
Không. Nó là phần của JavaBeans editor, không tự thay JSON serializer.

**9. Editor parse được một mã có đồng nghĩa mã đó hợp lệ để đặt hàng không?**  
Không. Parse xác nhận cú pháp/biểu diễn; quyền sử dụng, tồn tại trong catalog và điều kiện nghiệp vụ phải được kiểm tra riêng.

**10. Một field cùng kiểu `String` cần được trim riêng, nên đăng ký thế nào?**  
Dùng overload có `propertyPath`, ví dụ `registerCustomEditor(String.class, "customerName", new StringTrimmerEditor(true))`, tránh áp dụng rộng nếu không mong muốn.

**11. Khi nào nên chọn `Formatter<T>` thay vì `PropertyEditorSupport`?**  
Khi cần parse/print theo `Locale` và tích hợp cơ chế formatting của Spring cho UI. Editor vẫn phù hợp khi cần tương thích JavaBeans hoặc một binder cụ thể.

**12. `getJavaInitializationString()` có phải kết quả lưu vào database không?**  
Không. Nó phục vụ công cụ sinh một biểu thức mã Java có thể khởi tạo giá trị hiện tại.

## Tóm tắt

- `PropertyEditor`: **hợp đồng JavaBeans JDK** cho giá trị có kiểu và biểu diễn/chỉnh sửa dạng text.
- `PropertyEditorSupport`: **lớp tiện ích có trạng thái**, thuận tiện khi viết custom editor.
- `setAsText -> setValue -> getValue`: **parse text thành object**.
- `setValue -> getAsText`: **biểu diễn object thành text**.
- `BeanWrapper` và `DataBinder`: **gắn editor với property**; `DataBinder` có thể thu thập lỗi binding trong `BindingResult`.
- `registerCustomEditor`: xác định **type** và có thể **property path**; cấu hình phải nằm đúng phạm vi sử dụng.
- `PropertyEditorRegistrar`: nhóm đăng ký và **tạo instance editor mới**, tránh chia sẻ mutable state.
- `Converter`/`Formatter`: API Spring hiện đại có thể đơn giản và phù hợp hơn khi xây mới, đặc biệt với i18n.
- Conversion không thay **validation**, **authorization**, **giới hạn input** hoặc **JSON deserialization**.

## Tài liệu tham khảo chính thức

- [Oracle Java 17 — java.beans.PropertyEditor](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/PropertyEditor.html)
- [Oracle Java 17 — java.beans.PropertyEditorSupport](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/PropertyEditorSupport.html)
- [Oracle Java 17 — JavaBeans package summary](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/package-summary.html)
- [Spring Framework 6.2 — Data Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation/data-binding.html)
- [Spring Framework 6.2 — PropertyEditorRegistry API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/beans/PropertyEditorRegistry.html)
- [Spring Framework 6.2 — BeanWrapperImpl API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/beans/BeanWrapperImpl.html)
- [Spring Framework 6.2 — DataBinder API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.2 — PropertyEditorRegistrar API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/beans/PropertyEditorRegistrar.html)
- [Spring Framework 6.2 — Spring Type Conversion and Formatting](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html)
