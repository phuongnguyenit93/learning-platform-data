# PropertyEditorRegistrar và tái sử dụng quy tắc đăng ký trong Spring

Khi Spring cần chuyển chuỗi đầu vào thành một kiểu Java tùy biến, ta có thể tạo một `java.beans.PropertyEditor` và đăng ký nó vào `BeanWrapper` hoặc `DataBinder`. Nhưng nếu ứng dụng có nhiều bean, nhiều controller hoặc nhiều điểm thực hiện binding, việc chép lại các lời gọi `registerCustomEditor(...)` sẽ tạo mã trùng lặp và dễ cấu hình không đồng nhất.

**`org.springframework.beans.PropertyEditorRegistrar`** giải quyết vấn đề đó: gom **quy tắc đăng ký editor** vào một đối tượng có thể dùng lại. Mỗi lần nhận một `PropertyEditorRegistry`, registrar đăng ký các editor cần thiết cho registry ấy.

Hai ý quan trọng nhất:

1. **Tái sử dụng một registrar** để khai báo cùng bộ quy tắc ở nhiều nơi.
2. **Không chia sẻ cùng một instance `PropertyEditor`** giữa nhiều binder/thread: registrar phải tạo editor **mới cho mỗi lần đăng ký** vì PropertyEditor thường có trạng thái và không thread-safe.

Bài học tập trung vào cách thiết kế registrar, lý do cần nó, ví dụ Java 17+ sử dụng được với `BeanWrapper` và `DataBinder`, cách tích hợp Spring MVC/IoC container, cùng các lỗi thực tế cần tránh.

## 1. Đặt PropertyEditorRegistrar vào đúng bức tranh

Giả sử một domain model có kiểu tùy biến:

~~~java
public record OrderCode(String value) {}
~~~

Client gửi chuỗi `"ab-123"` nhưng object cần `OrderCode("AB-123")`. Một `PropertyEditor` có thể chuyển đổi:

~~~text
"ab-123" (String)
      |
      v
OrderCodeEditor.setAsText(...)
      |
      v
OrderCode("AB-123")
      |
      v
OrderForm.setOrderCode(...)
~~~

Nếu có hai bộ điều phối binding riêng, ta có thể gặp mã lặp:

~~~java
// Trong một BeanWrapper:
wrapper.registerCustomEditor(OrderCode.class, new OrderCodeEditor());

// Trong một DataBinder khác:
binder.registerCustomEditor(OrderCode.class, new OrderCodeEditor());
~~~

Các dòng trên là **đoạn trích**, không phải một chương trình hoàn chỉnh. Mỗi nơi phải biết chính xác loại editor và cách cấu hình. Khi thêm editor khác, nhiều vị trí có thể phải sửa.

Thay vào đó, định nghĩa **một registrar**:

~~~java
public final class OrderCodeRegistrar implements PropertyEditorRegistrar {
    @Override
    public void registerCustomEditors(PropertyEditorRegistry registry) {
        registry.registerCustomEditor(
                OrderCode.class, new OrderCodeEditor());
    }
}
~~~

Đây là một class minh họa; cần import hai interface Spring và có các class `OrderCode`, `OrderCodeEditor`. Khi sử dụng:

~~~java
PropertyEditorRegistrar registrar = new OrderCodeRegistrar();

registrar.registerCustomEditors(wrapper);
registrar.registerCustomEditors(binder);
~~~

**Cùng registrar**, nhưng lời gọi `new OrderCodeEditor()` được thực hiện riêng cho `wrapper` và `binder`. Nhờ vậy chúng có editor riêng, còn **quy tắc đăng ký** chỉ được viết ở một chỗ.

## 2. Phân biệt các interface và thành phần liên quan

| Thành phần | Package / kiểu | Vai trò |
| --- | --- | --- |
| `PropertyEditor` | `java.beans.PropertyEditor`, interface | Hợp đồng JavaBeans chuyển văn bản ↔ giá trị; editor có trạng thái `getValue()/setValue()` |
| `PropertyEditorSupport` | `java.beans.PropertyEditorSupport`, class | Lớp tiện ích để viết một custom PropertyEditor |
| `PropertyEditorRegistry` | `org.springframework.beans.PropertyEditorRegistry`, interface | Nơi đăng ký custom editor theo kiểu hoặc theo property path |
| `PropertyEditorRegistrar` | `org.springframework.beans.PropertyEditorRegistrar`, interface | Chiến lược **đăng ký một bộ editor** vào registry bất kỳ |
| `BeanWrapper` | `org.springframework.beans.BeanWrapper`, interface | Đọc/ghi JavaBean property và thực hiện conversion |
| `DataBinder` | `org.springframework.validation.DataBinder`, class | Nhận `PropertyValues`, gắn vào target, quản lý lỗi binding và validation |
| `WebDataBinder` | `org.springframework.web.bind.WebDataBinder` | Binder phù hợp với ngữ cảnh web |
| `CustomEditorConfigurer` | `org.springframework.beans.factory.config.CustomEditorConfigurer` | `BeanFactoryPostProcessor` cấu hình custom editor/registrar phục vụ **bean factory** |

`BeanWrapper` và `DataBinder` có thể làm `PropertyEditorRegistry`. Vì thế registrar **không cần biết** bên nhận là binder web, wrapper JavaBean hay binder được tạo thủ công; nó chỉ làm việc với API đăng ký chung.

### Chữ ký chính xác

~~~java
package org.springframework.beans;

public interface PropertyEditorRegistrar {
    void registerCustomEditors(PropertyEditorRegistry registry);
}
~~~

Khối trên là **rút gọn minh họa của hợp đồng API**, không phải file cần tự định nghĩa trong dự án. Trong một số phiên bản Spring 6.2.x hoặc mới hơn, interface còn có API mặc định phục vụ xử lý editor mặc định; điểm cốt lõi để ứng dụng tự triển khai vẫn là `registerCustomEditors(...)`.

Method nhận registry **từ bên ngoài**, trả về `void`. Nó không trả danh sách editor và cũng không tự được chạy chỉ vì class implements interface. Một thành phần gọi nó, chẳng hạn `@InitBinder` hoặc `CustomEditorConfigurer`, chịu trách nhiệm kích hoạt đăng ký.

## 3. Vì sao phải tạo editor mới mỗi lần đăng ký?

`PropertyEditorSupport` giữ **giá trị hiện tại** bên trong. Ví dụ editor có thể làm:

~~~java
@Override
public void setAsText(String text) {
    setValue(new OrderCode(text));
}
~~~

Đây là **đoạn trích method**, cần class editor và domain object phù hợp. Khi binder chuyển nhiều trường, nhiều object hoặc nhiều request, editor có thể bị gọi và thay đổi trạng thái. Một instance dùng đồng thời trên nhiều luồng có thể làm lẫn dữ liệu.

**Cách sai — lưu sẵn một editor trong registrar singleton:**

~~~java
// ĐOẠN CODE MINH HỌA ANTI-PATTERN, KHÔNG NÊN DÙNG.
public final class UnsafeRegistrar implements PropertyEditorRegistrar {
    private final OrderCodeEditor editor = new OrderCodeEditor();

    @Override
    public void registerCustomEditors(PropertyEditorRegistry registry) {
        registry.registerCustomEditor(OrderCode.class, editor);
    }
}
~~~

Khi registrar này được tái sử dụng, các registry có thể giữ **cùng một `editor` mutable**. Điều này phá hỏng ranh giới trạng thái và tạo rủi ro khi chạy song song.

**Cách đúng — tạo editor trong lời gọi registrar:**

~~~java
public final class SafeRegistrar implements PropertyEditorRegistrar {
    @Override
    public void registerCustomEditors(PropertyEditorRegistry registry) {
        registry.registerCustomEditor(
                OrderCode.class,
                new OrderCodeEditor());
    }
}
~~~

Hai đoạn chỉ để so sánh, chưa khai báo các import và class phụ thuộc. **Registrar có thể là singleton stateless**, vì bản thân nó không giữ state của editor; mỗi lần gọi `registerCustomEditors` tạo editor độc lập cho registry.

Nếu editor cần cấu hình không thay đổi, registrar có thể giữ **configuration bất biến** (ví dụ format pattern, timezone ID) và truyền vào constructor editor mới. Tránh chia sẻ những đối tượng không thread-safe như `SimpleDateFormat` giữa các editor. Với kiểu mới như `java.time.LocalDate`, nếu có thể, hãy cân nhắc một `Formatter` hoặc `Converter` thay vì custom PropertyEditor có trạng thái.

### Không hiểu nhầm phạm vi “mới”

“Editor mới cho mỗi lần gọi registrar” không có nghĩa Spring tạo một editor mới **cho từng ký tự** hay **mỗi field assignment**. Đơn vị nên suy nghĩ là **mỗi registry/binder được cấu hình**; một editor đã đăng ký có thể được sử dụng nhiều lần bên trong phạm vi registry đó.

Không nên dựa vào việc Spring tự sao chép editor cũ thành editor mới: chiến lược tạo instance mới là trách nhiệm của mã registrar.

## 4. Ví dụ Java 17+: một registrar dùng lại cho BeanWrapper và DataBinder

Ví dụ này chạy **không cần máy chủ HTTP và không cần Spring Boot**:

- Dữ liệu nguồn có mã đơn hàng `" ab-123 "` hoặc `" cd-456 "`.
- JavaBean cần property kiểu `OrderCode`, không phải `String`.
- `OrderCodeEditor` chuẩn hóa trim/uppercase, kiểm tra định dạng `AA-999`.
- `OrderCodeRegistrar` đăng ký editor cho bất kỳ `PropertyEditorRegistry`.
- Một instance registrar được dùng cho cả `BeanWrapperImpl` và `DataBinder`.
- Một thử nghiệm mã sai cho thấy lỗi conversion được ghi vào `BindingResult` khi dùng `DataBinder`.

### 4.1. Tạo Maven project

Dùng **JDK 17+**, Maven, một phiên bản Spring Framework đồng bộ. File `pom.xml` dưới đây ghim `spring-context:6.2.19` cho ví dụ (mục đích tái hiện, không khẳng định đó là bản mới nhất). Module `spring-context` cung cấp `DataBinder` và có phụ thuộc tới `spring-beans`.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>property-editor-registrar-demo</artifactId>
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
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Nếu ứng dụng thực tế dùng Spring Boot, nên để **Spring Boot BOM/parent** quản lý các module Spring cùng phiên bản, tránh ghim riêng `spring-context` khác dòng đang được Boot sử dụng.

### 4.2. Mã nguồn hoàn chỉnh

Tạo file **`src/main/java/example/PropertyEditorRegistrarDemo.java`**:

~~~java
package example;

import java.beans.PropertyEditorSupport;
import java.util.Locale;

import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.PropertyEditorRegistrar;
import org.springframework.beans.PropertyEditorRegistry;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public class PropertyEditorRegistrarDemo {

    // Kiểu giá trị domain: mã chuẩn hóa, khác với chuỗi request.
    public record OrderCode(String value) {
    }

    // PropertyEditor có trạng thái (inherited getValue/setValue).
    public static final class OrderCodeEditor extends PropertyEditorSupport {

        @Override
        public void setAsText(String text) throws IllegalArgumentException {
            if (text == null || text.isBlank()) {
                setValue(null);
                return;
            }

            String normalized = text.trim().toUpperCase(Locale.ROOT);

            if (!normalized.matches("[A-Z]{2}-[0-9]{3}")) {
                throw new IllegalArgumentException(
                        "Order code must match AA-999");
            }

            setValue(new OrderCode(normalized));
        }

        @Override
        public String getAsText() {
            OrderCode value = (OrderCode) getValue();
            return value == null ? "" : value.value();
        }
    }

    // Có thể chia sẻ registrar giữa các registry.
    // Nhưng editor mới được tạo cho mỗi lần registerCustomEditors.
    public static final class OrderCodeRegistrar
            implements PropertyEditorRegistrar {

        @Override
        public void registerCustomEditors(PropertyEditorRegistry registry) {
            registry.registerCustomEditor(
                    OrderCode.class, new OrderCodeEditor());
        }
    }

    // JavaBean đích: property binding sử dụng getter/setter.
    public static final class OrderForm {
        private OrderCode orderCode;
        private String note;

        public OrderCode getOrderCode() {
            return orderCode;
        }

        public void setOrderCode(OrderCode orderCode) {
            this.orderCode = orderCode;
        }

        public String getNote() {
            return note;
        }

        public void setNote(String note) {
            this.note = note;
        }
    }

    public static void main(String[] args) {

        // Đây là cùng một registrar, không phải cùng một editor.
        PropertyEditorRegistrar registrar = new OrderCodeRegistrar();

        OrderForm viaWrapper = new OrderForm();
        BeanWrapper wrapper = new BeanWrapperImpl(viaWrapper);
        registrar.registerCustomEditors(wrapper);

        wrapper.setPropertyValue("orderCode", " ab-123 ");
        wrapper.setPropertyValue("note", "Created through BeanWrapper");

        System.out.println(
                "beanWrapper.code=" + viaWrapper.getOrderCode().value());
        System.out.println(
                "beanWrapper.note=" + viaWrapper.getNote());

        OrderForm viaBinder = new OrderForm();
        DataBinder binder = new DataBinder(viaBinder, "orderForm");
        binder.setAllowedFields("orderCode", "note");
        registrar.registerCustomEditors(binder);

        MutablePropertyValues input = new MutablePropertyValues()
                .add("orderCode", " cd-456 ")
                .add("note", "Created through DataBinder");

        binder.bind(input);

        System.out.println(
                "dataBinder.code=" + viaBinder.getOrderCode().value());
        System.out.println(
                "dataBinder.note=" + viaBinder.getNote());
        System.out.println(
                "dataBinder.errors=" + binder.getBindingResult().getErrorCount());

        OrderForm invalid = new OrderForm();
        DataBinder invalidBinder = new DataBinder(invalid, "orderForm");
        invalidBinder.setAllowedFields("orderCode");
        registrar.registerCustomEditors(invalidBinder);

        invalidBinder.bind(
                new MutablePropertyValues().add("orderCode", "invalid"));

        BindingResult errors = invalidBinder.getBindingResult();
        System.out.println(
                "badBinder.hasErrors=" + errors.hasErrors());
        System.out.println(
                "badBinder.field=" + errors.getFieldError("orderCode").getField());
    }
}
~~~

**Đặc điểm quan trọng của mã:**

- `OrderCode` là record Java 17, có accessor `value()`.
- `OrderForm` là JavaBean có constructor mặc định và getter/setter để `BeanWrapper`/`DataBinder` gán property.
- Editor **không chỉnh sửa raw string**, mà tạo một giá trị domain mới `OrderCode(normalized)`.
- `PropertyEditorSupport` chứa trạng thái giá trị và cung cấp `setValue()/getValue()`; `getAsText()` chuyển ngược giá trị hiện tại sang chuỗi phục vụ biểu diễn.
- `registerCustomEditors(...)` tạo `new OrderCodeEditor()` **mỗi khi được gọi**.
- Cùng một registrar được dùng cho wrapper, binder hợp lệ và binder xử lý dữ liệu lỗi.
- Với `DataBinder`, exception từ `setAsText` khi định dạng sai được biến thành lỗi chuyển kiểu phù hợp trong `BindingResult`; đây không phải lỗi Jakarta Bean Validation.

### 4.3. Lệnh chạy và đầu ra

Cấu trúc thư mục:

~~~text
property-editor-registrar-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── PropertyEditorRegistrarDemo.java
~~~

Từ thư mục chứa `pom.xml`:

~~~bash
java -version
mvn -version
mvn -q compile exec:java -Dexec.mainClass=example.PropertyEditorRegistrarDemo
~~~

Với JDK 17+ và Maven tải được dependency, **đầu ra do chương trình in** là:

~~~text
beanWrapper.code=AB-123
beanWrapper.note=Created through BeanWrapper
dataBinder.code=CD-456
dataBinder.note=Created through DataBinder
dataBinder.errors=0
badBinder.hasErrors=true
badBinder.field=orderCode
~~~

Maven có thể in log khác tùy môi trường. Những dòng ở trên được xác định bởi các câu lệnh `System.out.println` của ví dụ. Lệnh `javac` thuần sẽ không đủ vì Spring không thuộc JDK; Maven chịu trách nhiệm classpath và biên dịch.

### 4.4. Phân tích kết quả

**Với BeanWrapper:**

`wrapper.setPropertyValue("orderCode", " ab-123 ")` tìm property `orderCode` có kiểu `OrderCode`, sử dụng editor đã đăng ký, gọi `setAsText` và gán `OrderCode("AB-123")` vào form. Vì chỉ có custom editor cho `OrderCode`, property `note` kiểu `String` vẫn được gán bình thường.

**Với DataBinder:**

`binder.bind(input)` đọc hai cặp giá trị từ `MutablePropertyValues`, kiểm soát allowed fields, chuyển `" cd-456 "` thành `OrderCode("CD-456")`, rồi gọi setter. `dataBinder.errors=0` vì dữ liệu hợp lệ. Trong ví dụ, `binder.setAllowedFields(...)` được dùng để minh họa việc cho phép gán có kiểm soát — registrar **không đảm nhiệm** bảo mật.

**Với dữ liệu sai:**

`"invalid"` không khớp mẫu `AA-999`. Editor ném `IllegalArgumentException`; `DataBinder` bắt và lưu thông tin lỗi binding cho field `orderCode`. Vì vậy `badBinder.hasErrors=true` và `badBinder.field=orderCode`. Thông tin chi tiết của message lỗi có thể phụ thuộc cấu hình, nên ví dụ không khẳng định một thông báo nội bộ cố định.

**Điều quan trọng nhất:** `PropertyEditorRegistrar` **không tự thực hiện binding hoặc validation**. Nó chỉ **cài quy tắc chuyển kiểu** vào đúng registry trước khi thao tác binding diễn ra.

## 5. Đăng ký nhiều editor và kiểm soát phạm vi

Một registrar có thể đăng ký **nhiều** editor:

~~~java
@Override
public void registerCustomEditors(PropertyEditorRegistry registry) {
    registry.registerCustomEditor(
            OrderCode.class, new OrderCodeEditor());

    registry.registerCustomEditor(
            Locale.class, new CustomLocaleEditor());
}
~~~

Đây là **đoạn trích**; cần thêm import `java.util.Locale` và `org.springframework.beans.propertyeditors.CustomLocaleEditor`. Nếu đăng ký editor cho `Locale.class`, toàn bộ các property kiểu `Locale` trong registry được xét theo editor đã cài, khi phù hợp.

Interface `PropertyEditorRegistry` có hai overload chính:

~~~java
void registerCustomEditor(
        Class<?> requiredType, PropertyEditor propertyEditor);

void registerCustomEditor(
        Class<?> requiredType, String propertyPath,
        PropertyEditor propertyEditor);
~~~

Đây là **chữ ký mô tả API**, không phải method cần khai báo lại. Tham số `propertyPath` có thể dùng để giới hạn editor cho một property cụ thể. Ví dụ:

~~~java
registry.registerCustomEditor(
        OrderCode.class, "billing.orderCode",
        new OrderCodeEditor());
~~~

Đây là **đoạn trích**, giả định model có property lồng nhau `billing.orderCode`. Một editor theo kiểu `OrderCode.class` áp dụng cho các property phù hợp kiểu đó; một editor theo property path dùng cho trường chỉ định. Cơ chế ưu tiên của Spring có thể xét cả type và path khi tìm editor; cần kiểm thử nếu đăng ký hai editor chồng lấn nhau.

**Vì sao phân biệt hai kiểu đăng ký?**

- Theo **type**: phù hợp khi mọi `OrderCode` trong phạm vi binder có cùng quy tắc parse/format.
- Theo **property path**: phù hợp khi một field cụ thể cần format khác, ví dụ một trường legacy có quy tắc riêng.
- Không đăng ký một editor cho collection và một editor cho từng phần tử trên **cùng một path** mà không đọc kỹ quy tắc của `PropertyEditorRegistry`; có thể tạo tình huống lựa chọn editor gây nhầm lẫn.

Nếu cần những quy tắc khác nhau theo ngữ cảnh nghiệp vụ, đừng ép tất cả vào một registrar quá rộng. Có thể thiết kế các registrar riêng cho nhóm domain khác nhau, hoặc cho phép registrar nhận cấu hình bất biến.

## 6. Tái sử dụng trong Spring MVC với @InitBinder

Trong Spring MVC, một `@Controller` hoặc `@ControllerAdvice` có thể khai báo `@InitBinder` để cấu hình `WebDataBinder` trước khi gán dữ liệu request vào model attribute.

Ý tưởng tích hợp:

~~~java
@Controller
public class OrderController {

    private final PropertyEditorRegistrar registrar;

    public OrderController(PropertyEditorRegistrar registrar) {
        this.registrar = registrar;
    }

    @InitBinder("orderForm")
    void initBinder(WebDataBinder binder) {
        registrar.registerCustomEditors(binder);
        binder.setAllowedFields("orderCode", "note");
    }

    @PostMapping("/orders")
    String submit(
            @ModelAttribute("orderForm") OrderForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "order-form";
        }
        return "order-success";
    }
}
~~~

**Đây là trích đoạn mô tả tích hợp**, không phải chương trình độc lập: cần import annotation MVC, `WebDataBinder`, `BindingResult`, tạo bean `PropertyEditorRegistrar` và đặt `OrderForm` trong phạm vi truy cập phù hợp. `"order-form"` và `"order-success"` là tên view, cần view templates hoặc đổi sang kiểu controller trả body tùy ứng dụng.

Có thể tạo bean registrar:

~~~java
@Configuration
class EditorRegistrationConfig {

    @Bean
    PropertyEditorRegistrar orderCodeRegistrar() {
        return new PropertyEditorRegistrarDemo.OrderCodeRegistrar();
    }
}
~~~

Đây là **đoạn trích configuration**, cần các import `@Configuration`, `@Bean`, `PropertyEditorRegistrar` và class ví dụ ở phần 4 trong cùng package hoặc được import. Trong ứng dụng thực tế, thường tách `OrderCodeRegistrar` và các domain/editor thành các class riêng để nhiều module dùng được.

Một lần request mới có thể tạo một `WebDataBinder` mới. Khi `@InitBinder` gọi registrar, nó tạo editor mới cho binder ấy. Registrar có thể là **singleton Spring bean** được nhiều controller dùng chung mà vẫn tránh chia sẻ state mutable của editor.

### Dùng @ControllerAdvice để áp dụng cho nhiều controller

Nếu nhiều controller đều sử dụng `OrderCode`, có thể chuyển quy tắc đăng ký chung vào advice:

~~~java
@ControllerAdvice
public class SharedEditorAdvice {

    private final PropertyEditorRegistrar registrar;

    public SharedEditorAdvice(PropertyEditorRegistrar registrar) {
        this.registrar = registrar;
    }

    @InitBinder
    void configure(WebDataBinder binder) {
        registrar.registerCustomEditors(binder);
    }
}
~~~

Đây cũng là **đoạn trích tích hợp**, cần bean registrar và import Spring MVC. `@ControllerAdvice` cho phép chia sẻ xử lý binder giữa các controller thuộc phạm vi advice. Tùy yêu cầu có thể giới hạn advice bằng base package, annotation hoặc assignable type, hoặc giới hạn `@InitBinder("orderForm")` theo tên model attribute. Không vô tình đăng ký editor phạm vi rộng cho những controller không cần nó.

**Lưu ý:** đăng ký cho controller `@InitBinder` không tự làm cho bean factory dùng các editor ấy khi khởi tạo bean cấu hình; đây là **hai cơ chế và hai phạm vi khác nhau**.

## 7. Tái sử dụng trong IoC container với CustomEditorConfigurer

Một mục đích khác là cho **Spring bean factory** sử dụng custom editors khi chuyển cấu hình kiểu chuỗi thành kiểu domain trong quá trình tạo/cấu hình bean. Spring cung cấp `CustomEditorConfigurer`, một `BeanFactoryPostProcessor`, để đăng ký registrar với bean factory.

### Cấu hình XML minh họa

~~~xml
<bean id="orderCodeRegistrar"
      class="example.OrderCodeRegistrar"/>

<bean class="org.springframework.beans.factory.config.CustomEditorConfigurer">
    <property name="propertyEditorRegistrars">
        <list>
            <ref bean="orderCodeRegistrar"/>
        </list>
    </property>
</bean>
~~~

Đây là **mảnh XML cấu hình** theo cơ chế Spring, không phải file độc lập; `example.OrderCodeRegistrar` ở đây giả định bạn đã tách registrar thành một **class top-level** public trong package `example`. Khi chỉ dùng class lồng từ ví dụ `PropertyEditorRegistrarDemo.OrderCodeRegistrar`, tên class Java nhị phân khác và XML phải điều chỉnh; cách đơn giản là tách nó thành file `OrderCodeRegistrar.java`.

Configurer đăng ký **chiến lược registrar** để bean factory có thể tạo editor cho từng quy trình tạo bean khi cần. Nó không dùng một instance editor dùng chung cho mọi bean.

### Cấu hình Java-based

Nếu sử dụng `@Configuration`, có thể định nghĩa `CustomEditorConfigurer` là bean post-processor:

~~~java
@Configuration
public class BeanFactoryEditorConfiguration {

    @Bean
    static CustomEditorConfigurer customEditorConfigurer() {
        CustomEditorConfigurer configurer = new CustomEditorConfigurer();
        configurer.setPropertyEditorRegistrars(
                new PropertyEditorRegistrar[]{
                        new OrderCodeRegistrar()
                });
        return configurer;
    }
}
~~~

Đây là **trích đoạn cấu hình**, giả định có class top-level `OrderCodeRegistrar` và đầy đủ import Spring. Việc khai báo `@Bean static` đối với `BeanFactoryPostProcessor` thường được khuyên dùng để tránh khởi tạo sớm `@Configuration` chứa bean. Quan trọng là `setPropertyEditorRegistrars(...)` nhận **mảng registrar**, không phải mảng `PropertyEditor`.

**Sự khác nhau về scope:**

| Cách đăng ký | Registry được cấu hình | Công dụng |
| --- | --- | --- |
| `registrar.registerCustomEditors(wrapper)` | Một `BeanWrapper` tự tạo | Đọc/ghi property trong đoạn mã Java trực tiếp |
| `registrar.registerCustomEditors(binder)` | Một `DataBinder` | Binding một target, lấy `BindingResult` |
| `@InitBinder` trong controller | `WebDataBinder` theo ngữ cảnh request | Chuyển input form/model attribute |
| `@ControllerAdvice + @InitBinder` | Các binder thuộc controller phù hợp advice | Dùng chung quy tắc cho nhiều controller |
| `CustomEditorConfigurer` | Bean factory / container IoC | Chuyển đổi property trong quá trình tạo/config bean |

**Không giả định** chỉ cấu hình `CustomEditorConfigurer` là tất cả `WebDataBinder` trong MVC đều tự động nhận editor cho form. Với custom request binding, hãy cấu hình binder/web binding initializer/advice phù hợp và kiểm thử endpoint thực tế.

### Có bắt buộc dùng CustomEditorConfigurer không?

Không. Nếu ứng dụng chỉ có vài controller nhận form, `@InitBinder` hoặc `@ControllerAdvice` thường rõ ràng hơn. `CustomEditorConfigurer` hữu ích khi chính **bean factory** cần cùng quy tắc chuyển kiểu để thiết lập properties của bean trong container.

Trong Spring Boot hiện đại, nhiều trường hợp nên dùng `Converter`/`Formatter` thông qua `ConversionService` thay vì cấu hình PropertyEditor cấp container; cách nào phù hợp phụ thuộc kiểu dữ liệu, yêu cầu kế thừa legacy và phạm vi chuyển đổi.

## 8. PropertyEditorRegistrar khác Converter và Formatter

Tất cả đều có thể liên quan chuyển kiểu, nhưng thiết kế khác nhau:

| Công cụ | Mô hình | Thích hợp khi |
| --- | --- | --- |
| `PropertyEditor` | JavaBeans editor mutable, giữ state giá trị | Tích hợp API cũ, chỉnh sửa field/bean bằng cơ chế PropertyEditor |
| `PropertyEditorRegistrar` | **Cấu hình đăng ký** nhiều PropertyEditor cho registry | Có PropertyEditor cần dùng lại tại nhiều binder/BeanWrapper/container |
| `Converter<S,T>` | Hàm chuyển từ kiểu `S` sang `T` | Quy tắc chuyển kiểu nhỏ gọn, có thể đăng ký vào `ConversionService` |
| `Formatter<T>` | Parse/print dữ liệu văn bản theo locale | Giá trị hiển thị form như ngày tháng, tiền tệ hoặc số theo locale |
| `ConversionService` | Registry thực thi converter/formatter | Cấu hình chuyển kiểu dùng chung nhiều nơi theo cơ chế hiện đại |

Ví dụ với `Converter<String, OrderCode>`, bạn có thể viết:

~~~java
public final class StringToOrderCodeConverter
        implements Converter<String, OrderCode> {

    @Override
    public OrderCode convert(String source) {
        String normalized = source.trim().toUpperCase(Locale.ROOT);
        if (!normalized.matches("[A-Z]{2}-[0-9]{3}")) {
            throw new IllegalArgumentException("Invalid order code");
        }
        return new OrderCode(normalized);
    }
}
~~~

Đây là **đoạn trích**, cần các import `org.springframework.core.convert.converter.Converter`, `java.util.Locale` và class `OrderCode`. Nó **không phải** mã có thể dán trực tiếp vào `PropertyEditorRegistrarDemo.java` mà không điều chỉnh class/import.

`Converter` không có trạng thái kiểu `getValue()/setValue()` giống `PropertyEditorSupport`; với converter stateless, việc chia sẻ singleton thường dễ quản lý hơn. Nếu đang viết ứng dụng Spring mới, hãy cân nhắc `Converter`/`Formatter` trước; nếu phải tích hợp một tập `PropertyEditor` đang có, `PropertyEditorRegistrar` là cơ chế đóng gói phù hợp.

**Không nhầm:** registrar không phải một `ConverterFactory`, không tự động đăng ký converter vào `ConversionService` và không làm nhiệm vụ validation.

## 9. Phân biệt chuyển kiểu, binding, validation và authorization

Một request có thể gửi:

~~~text
orderCode=ab-123
note=Ship today
isAdmin=true
~~~

Quá trình xử lý nên được tách thành bốn câu hỏi:

1. **Conversion:** `"ab-123"` có chuyển thành `OrderCode("AB-123")` không? — `OrderCodeEditor` thực hiện.
2. **Binding:** trường nào từ request được gán lên JavaBean? — `DataBinder`/`WebDataBinder` và các quy tắc property binding quyết định.
3. **Validation:** mã đơn hàng có tồn tại, được phép đặt, nghiệp vụ hợp lệ không? — `Validator`/Jakarta Validation/service thực hiện.
4. **Authorization:** người gọi có quyền thao tác với object/field đó không? — kiểm soát bảo mật/service thực hiện.

**Một registrar thành công không bảo đảm ba việc còn lại thành công.**

Trong ví dụ Java, `setAllowedFields("orderCode", "note")` giới hạn property binding vào hai field. `isAdmin` không được cho phép nếu client cố gửi lên. Khi field bị chặn, nên kiểm tra `BindingResult#getSuppressedFields()` nếu chính sách cần ghi log hoặc từ chối request. Đừng chỉ nhìn `hasErrors()` vì suppressed field không nhất thiết tự sinh lỗi binding.

Dùng DTO dành riêng cho từng request để tránh **mass assignment** trên entity có nhiều setter nhạy cảm. Với dữ liệu không tin cậy, không chỉ dựa vào việc editor kiểm tra định dạng chuỗi.

### Không làm sạch dữ liệu nhạy cảm bằng quy tắc quá rộng

Editor của bài chỉ dành cho `OrderCode`, và hành vi trim/uppercase là hợp đồng có chủ đích của domain đó. Không dùng cùng một editor tùy tiện cho tất cả `String`: mật khẩu, mã chữ ký, token hoặc văn bản tự do có thể phân biệt chữ hoa/thường và khoảng trắng. Đăng ký theo **domain type** hoặc **property path** cụ thể giúp giới hạn tác động.

## 10. Những lỗi thường gặp và cách sửa

### Lỗi 1: registrar tạo editor một lần rồi dùng chung

**Sai:** một field `private final OrderCodeEditor editor` nằm trên registrar singleton và được đăng ký vào mọi binder.

**Đúng:** tạo `new OrderCodeEditor()` **bên trong** `registerCustomEditors(...)` cho từng registry. Có thể giữ các tham số cấu hình bất biến trên registrar.

### Lỗi 2: viết registrar nhưng quên gọi

Chỉ triển khai `PropertyEditorRegistrar` không làm Spring tự động tìm và đăng ký editor. Cần gọi `registerCustomEditors(...)` hoặc kết nối registrar vào `@InitBinder`, `CustomEditorConfigurer` hay cơ chế tương đương.

### Lỗi 3: import nhầm PropertyEditor

Interface editor là **`java.beans.PropertyEditor`**; registrar và registry là **`org.springframework.beans.*`**. `PropertyEditorSupport` thuộc JDK, không thuộc Spring.

### Lỗi 4: đăng ký vào sai phạm vi

Configurer cho IoC container chủ yếu hỗ trợ chuyển giá trị khi bean factory tạo/cấu hình bean. Nó không thay thế việc cấu hình một `WebDataBinder` của controller. Ngược lại, `@InitBinder` của một controller không tự cấu hình mọi bean trong `ApplicationContext`.

### Lỗi 5: thay đổi state của editor trong nhiều request

`setAsText` và `setValue` thay đổi state. Nếu nhiều request dùng cùng instance editor, giá trị hiện tại có thể bị ghi đè. Khả năng share thread-safe thuộc registrar stateless, **không phải editor mutable**.

### Lỗi 6: editor xử lý sai null, rỗng và khoảng trắng

Các chuỗi `null`, `""`, `"   "` có thể khác ý nghĩa nghiệp vụ. Ví dụ trong bài chuyển cả ba thành `null`. Nhưng đây chỉ là lựa chọn của bài; ứng dụng cần quyết định rõ liệu field bắt buộc, có default hay cho phép xóa giá trị.

### Lỗi 7: parse lỗi làm ứng dụng dừng không mong muốn

`setAsText` có thể ném `IllegalArgumentException` cho chuỗi sai định dạng. Với `DataBinder`, lỗi chuyển kiểu thường được biểu diễn thành `FieldError`; với `BeanWrapper.setPropertyValue` trực tiếp, lỗi có thể được ném cho caller. Hãy bắt/đọc kết quả đúng theo API và không nuốt lỗi rồi tiếp tục xử lý dữ liệu sai.

### Lỗi 8: bỏ qua custom editor khi đổi sang ConversionService

Ứng dụng có thể có nhiều nguồn chuyển kiểu: default editors, custom editors, ConversionService, formatter, annotation. Nếu một kiểu được đăng ký ở nhiều nơi, hành vi ưu tiên có thể gây bất ngờ. Hãy kiểm thử đúng binding path thực tế thay vì chỉ test converter bằng tay.

### Lỗi 9: dùng getAsText mà quên setAsText

`getAsText` phục vụ biểu diễn giá trị ra chuỗi; `setAsText` là đường parse chuỗi thành object. Với bi-directional editing/form display, cả hai có thể cần được triển khai nhất quán. Nếu chỉ parse form input, đừng giả định mặc định của `PropertyEditorSupport#getAsText` luôn có format mong muốn.

### Lỗi 10: đưa validation/authorization vào editor không đúng chỗ

Kiểm tra cú pháp mã `AA-999` tại editor có thể hợp lý cho conversion. Nhưng kiểm tra mã đã được cấp quyền cho người dùng hay có tồn tại trong database hay không không nên được xem là trách nhiệm của registrar. Tách lớp conversion khỏi domain validation và authorization.

### Lỗi 11: chọn editor cho tất cả String

Đăng ký editor toàn cục cho `String.class` có thể tác động đến nhiều property khác không cùng hợp đồng. Nên đăng ký theo kiểu domain chuyên biệt hoặc theo đường dẫn field, hoặc dùng formatter/converter có chính sách rõ ràng.

### Lỗi 12: không kiểm thử nhiều registry

Nếu chỉ test `OrderCodeEditor` riêng, vẫn có thể quên đăng ký editor trong `WebDataBinder` hoặc `BeanWrapper` cụ thể. Test mỗi ngữ cảnh mà ứng dụng thực sự cần: bean factory, wrapper, controller/advice, binding hợp lệ và binding sai.

## 11. Checklist và bài tập tự kiểm tra

**Checklist triển khai một registrar dùng lại:**

1. Xác định kiểu domain mà chuỗi request cần chuyển đổi; giới hạn phạm vi type/path.
2. Viết một `PropertyEditorSupport` với `setAsText`, `getAsText` và xử lý null/invalid theo hợp đồng.
3. Tạo class stateless implementing `PropertyEditorRegistrar`.
4. Trong **mỗi lần** `registerCustomEditors(registry)`, gọi `new` để tạo editor riêng, không dùng singleton editor.
5. Đăng ký vào đúng phạm vi: `BeanWrapper`, `DataBinder`, `@InitBinder` hoặc `CustomEditorConfigurer`.
6. Với request bên ngoài, áp dụng DTO/allowed fields và quy tắc authorization độc lập.
7. Kiểm thử dữ liệu đúng, sai, rỗng; ghi nhận lỗi conversion và bảo đảm không chia sẻ state giữa binders.
8. Nếu triển khai mới, đánh giá liệu `Converter`/`Formatter` cùng `ConversionService` có thích hợp hơn không.

**Câu hỏi tự kiểm tra:**

1. Vì sao một `PropertyEditorRegistrar` có thể là singleton nhưng `PropertyEditor` lại không nên chia sẻ?
2. `PropertyEditorRegistry` khác `PropertyEditorRegistrar` ở điểm nào?
3. `registerCustomEditor(OrderCode.class, editor)` và overload thêm `"orderForm.orderCode"` khác nhau về phạm vi ra sao? Cần xác minh tên property path nào đối với registry thực tế?
4. `CustomEditorConfigurer` có tự động đảm bảo mọi `@ModelAttribute` trong Spring MVC dùng cùng editor không?
5. Khi `DataBinder.bind(...)` nhận `"invalid"`, lỗi thuộc **conversion** hay **validation nghiệp vụ**?
6. Tại sao nên giữ quy tắc chuyển mã `AA-999` trong editor, nhưng quyền sửa đơn hàng lại ở service/security?
7. Nếu một app có rất nhiều controller cần cùng editor, cách nào giảm lặp `@InitBinder` nhưng vẫn bảo đảm mỗi binder có editor mới?
8. Khi viết dự án mới, lý do nào khiến bạn ưu tiên `Converter<String,OrderCode>` hơn `PropertyEditorSupport`?

**Ghi nhớ:** `PropertyEditorRegistrar` là **bản thiết kế đăng ký** có thể tái sử dụng; mỗi lần nó nhận một registry, hãy tạo **những instance editor mới** rồi đăng ký theo type hoặc property path. Khi chia sẻ quy tắc giữa bean factory và web binder, phải **đăng ký ở từng phạm vi cần thiết**. Registrar không thay thế binding, validation hay authorization.

## Tài liệu chính thức

- [Spring Framework Reference — Data Binding / PropertyEditorRegistrar](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring Framework Javadoc — PropertyEditorRegistrar](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/PropertyEditorRegistrar.html)
- [Spring Framework Javadoc — PropertyEditorRegistry](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/PropertyEditorRegistry.html)
- [Spring Framework Javadoc — DataBinder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework Javadoc — CustomEditorConfigurer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/config/CustomEditorConfigurer.html)
- [Spring Framework MVC Reference — @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework WebFlux Reference — DataBinder](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-initbinder.html)
- [Oracle Java SE — PropertyEditor](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/PropertyEditor.html)
- [Oracle Java SE — PropertyEditorSupport](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/PropertyEditorSupport.html)