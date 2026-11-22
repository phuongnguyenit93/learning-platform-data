# Quy ước tìm lớp editor theo tên kiểu dữ liệu trong Spring Framework

Trong cơ chế **JavaBeans PropertyEditor**, mỗi kiểu dữ liệu Java có thể có một lớp **editor** chuyên chuyển giữa biểu diễn văn bản và đối tượng của kiểu đó. Thay vì phải đăng ký editor cho từng trường hợp, JavaBeans đưa ra một quy ước đặt tên để tìm lớp editor dựa trên **tên của kiểu đích**. Spring Framework hỗ trợ và sử dụng hạ tầng JavaBeans này khi xử lý nhiều tình huống cấu hình bean và data binding.

Quy tắc dễ nhớ nhất:

> Nếu kiểu dữ liệu là `com.example.domain.TicketCode` thì lớp `com.example.domain.TicketCodeEditor`, **cùng package** và có tên là **tên kiểu + `Editor`**, có thể được JavaBeans tìm thấy tự động mà không cần đăng ký tên editor thủ công.

Quy ước đó **không** có nghĩa mọi class kết thúc bằng `Editor` tự được Spring MVC/JSON dùng, không phải cơ chế component scan, và không thay thế tất cả những con đường chuyển kiểu hiện đại như `ConversionService`.

## 1. Vì sao cần tìm PropertyEditor?

Một property có kiểu Java cụ thể nhưng nguồn dữ liệu có thể là String:

~~~text
application property / XML bean definition / form parameter
                         |
                         v
                 "tkt-007"  (String)
                         |
                         v
            Chọn editor cho TicketCode
                         |
                         v
               TicketCodeEditor
                         |
                         v
               TicketCode("TKT-007")
                         |
                         v
             property có kiểu TicketCode
~~~

Interface `java.beans.PropertyEditor` mô tả khả năng thao tác một giá trị và biểu diễn văn bản của nó. Trong code thực tế, thường kế thừa `java.beans.PropertyEditorSupport` rồi override:

- `setAsText(String)`: phân tích text thành giá trị kiểu đích, thường gọi `setValue(...)`.
- `getAsText()`: xuất giá trị hiện tại thành String.
- `getValue()` / `setValue(Object)`: đọc/ghi giá trị editor đang giữ.

Editor **có trạng thái**: giá trị hiện tại nằm trong instance của editor. Vì vậy không nên lấy một instance mutable rồi dùng đồng thời cho nhiều request/luồng. Khi đăng ký bằng factory/registrar, nên cấp instance mới cho mỗi quá trình binding thích hợp.

Trong Spring, `BeanWrapperImpl` và `DataBinder` có thể dùng `PropertyEditor`. Nhưng việc **tìm được lớp editor** và việc **một subsystem của Spring chọn sử dụng editor đó** là hai bước cần phân biệt.

## 2. Thứ tự tìm editor của `PropertyEditorManager`

JavaBeans cung cấp class `java.beans.PropertyEditorManager` trong module JDK `java.desktop`, với method:

~~~java
PropertyEditor editor = PropertyEditorManager.findEditor(TargetType.class);
~~~

Theo API Java SE 17, manager sử dụng ba kỹ thuật theo thứ tự:

| Thứ tự | Cách tìm | Ví dụ đối với `com.example.domain.TicketCode` |
| --- | --- | --- |
| 1 | Editor đã đăng ký rõ bằng `registerEditor(targetType, editorClass)` | Lớp editor đã đăng ký cho `TicketCode.class` |
| 2 | Lấy **fully qualified class name** của kiểu đích và nối hậu tố `Editor` | `com.example.domain.TicketCodeEditor` |
| 3 | Lấy **simple class name** cộng `Editor` rồi tìm trong các package thuộc **editor search path** | `com.example.editors.TicketCodeEditor` nếu `com.example.editors` có trong search path |

Nếu không tìm được editor phù hợp, `findEditor(...)` có thể trả về **`null`**. Đây không phải lời bảo đảm mọi kiểu đều có cách tự chuyển đổi.

### 2.1. Quy tắc cùng package là trường hợp phổ biến

Với cấu trúc:

~~~text
src/main/java/
  com/example/domain/
    TicketCode.java
    TicketCodeEditor.java
~~~

JavaBeans có thể tìm `com.example.domain.TicketCodeEditor` cho `TicketCode.class`. Không phải viết một dòng `PropertyEditorManager.registerEditor(...)` trong trường hợp này, miễn là lớp editor hợp lệ, có thể được nạp/khởi tạo, nằm trên classpath/module path phù hợp và không gặp trở ngại từ cơ chế đóng gói module.

Nói chính xác: **Editor nằm cạnh kiểu mà nó chỉnh sửa**, không nhất thiết nằm cạnh class sử dụng kiểu đó. Nếu `OrderForm` ở `com.example.web` nhưng property `code` có kiểu `com.example.domain.TicketCode`, đường tìm theo tên là `com.example.domain.TicketCodeEditor`, **không phải** `com.example.web.TicketCodeEditor`.

Tên phải khớp cả phần hậu tố:

- `TicketCode` → `TicketCodeEditor`.
- `CustomerId` → `CustomerIdEditor`.
- `MoneyAmount` → `MoneyAmountEditor`.

Tên `TicketCodeConverter`, `TicketCodePropertyEditor` hoặc `CodeEditor` **không khớp mặc định** với quy tắc `TicketCodeEditor`, dù các class đó có thể dùng được nếu được đăng ký rõ bằng cơ chế tương ứng.

### 2.2. Đăng ký tường minh được ưu tiên

Có thể bỏ qua quy tắc cùng package bằng cách khai báo:

~~~java
PropertyEditorManager.registerEditor(
        TicketCode.class, TicketCodeEditor.class);
~~~

`registerEditor` nhận **class của kiểu đích và class của editor**, không nhận sẵn một editor instance. Lần tìm bằng `findEditor(...)` sẽ ưu tiên thông tin đã đăng ký trước khi thử đoán tên. Có thể hủy đăng ký bằng cách truyền `null` làm `editorClass` theo API JavaBeans.

Lưu ý: `PropertyEditorManager` quản lý đăng ký/search path ở phạm vi cơ chế JavaBeans của runtime, không tương đương một bean của riêng controller. Không nên đặt các thay đổi toàn cục trong request handler. Các test dùng chung JVM cũng cần tránh làm bẩn trạng thái đăng ký của nhau.

### 2.3. Tìm trong editor search path

Nếu editor đặt trong một package riêng:

~~~text
src/main/java/
  com/example/domain/TicketCode.java
  com/example/editors/TicketCodeEditor.java
~~~

và lớp này không nằm cùng package với kiểu đích, vẫn có thể tìm bằng search path:

~~~java
String[] original = PropertyEditorManager.getEditorSearchPath();
PropertyEditorManager.setEditorSearchPath(
        new String[] { "com.example.editors" });
~~~

Sau đó `findEditor(TicketCode.class)` có thể tìm `com.example.editors.TicketCodeEditor` ở bước thứ ba.

**Quan trọng:** `setEditorSearchPath(...)` **thay toàn bộ danh sách hiện tại**, không tự nối một package vào danh sách cũ. Nếu muốn giữ path trước đó, phải tạo mảng mới gồm các phần tử ban đầu cộng thêm package cần thiết. Danh sách mặc định là **phụ thuộc JDK implementation**; không nên hard-code hoặc dựa vào internal package `sun.*` như một API ổn định của ứng dụng.

Trong dự án Spring hiện đại, thường dễ theo dõi hơn nếu đăng ký editor vào đúng `DataBinder`, `BeanWrapper` hoặc container thay vì sửa search path toàn JVM.

## 3. Ví dụ Java 17+ chạy được mà không cần Spring

Ví dụ này kiểm chứng trực tiếp **quy tắc JavaBeans**, tránh nhầm hiện tượng tự tìm với các editor do Spring đăng ký mặc định. Tạo **ba file** đúng tên và package sau.

### 3.1. Kiểu dữ liệu: `TicketCode`

File `src/main/java/com/example/domain/TicketCode.java`:

~~~java
package com.example.domain;

public record TicketCode(String value) {

    public TicketCode {
        if (value == null || !value.matches("TKT-[0-9]{3}")) {
            throw new IllegalArgumentException(
                    "Ticket code must match TKT-nnn");
        }
    }
}
~~~

`TicketCode` là Java record, có bất biến về định dạng. Cách đặt tên `TicketCodeEditor` không dựa vào việc kiểu đích phải là JavaBean có setter: manager tìm editor dựa trên **Class của kiểu đích**.

### 3.2. Editor cùng package: `TicketCodeEditor`

File `src/main/java/com/example/domain/TicketCodeEditor.java`:

~~~java
package com.example.domain;

import java.beans.PropertyEditorSupport;
import java.util.Locale;

public final class TicketCodeEditor extends PropertyEditorSupport {

    public TicketCodeEditor() {
    }

    @Override
    public void setAsText(String text) {
        if (text == null || text.isBlank()) {
            setValue(null);
            return;
        }
        String normalized = text.strip().toUpperCase(Locale.ROOT);
        setValue(new TicketCode(normalized));
    }

    @Override
    public String getAsText() {
        TicketCode code = (TicketCode) getValue();
        return code == null ? "" : code.value();
    }
}
~~~

Editor ở **cùng package** với `TicketCode`, có tên **chính xác** `TicketCodeEditor`, là public class và có **public no-argument constructor**. Những điều này giúp hạ tầng JavaBeans có thể tạo instance khi tìm thấy class.

Quy tắc chuyển đổi trong ví dụ:

- `" tkt-007 "` → `TicketCode("TKT-007")`.
- `"TKT-007"` → `TicketCode("TKT-007")`.
- `null` hoặc chuỗi toàn khoảng trắng → `null`.
- `"bad"` → `IllegalArgumentException` từ constructor `TicketCode`.

Chọn `Locale.ROOT` cho mã định danh mang tính kỹ thuật để kết quả đổi chữ hoa không phụ thuộc locale mặc định của máy. Với dữ liệu hiển thị phụ thuộc ngôn ngữ/khu vực, cân nhắc dùng formatter có `Locale` thay vì áp dụng chính sách chuẩn hóa này cho mọi String.

### 3.3. Main: tìm và gọi editor bằng `PropertyEditorManager`

File `src/main/java/com/example/app/EditorLookupDemo.java`:

~~~java
package com.example.app;

import java.beans.PropertyEditor;
import java.beans.PropertyEditorManager;
import com.example.domain.TicketCode;
import com.example.domain.TicketCodeEditor;

public final class EditorLookupDemo {

    public static void main(String[] args) {
        // Không đăng ký editor trước lệnh findEditor đầu tiên.
        PropertyEditor editor =
                PropertyEditorManager.findEditor(TicketCode.class);

        if (editor == null) {
            throw new IllegalStateException("No editor for TicketCode");
        }

        System.out.println("automatic: "
                + editor.getClass().getSimpleName());

        editor.setAsText(" tkt-007 ");
        TicketCode code = (TicketCode) editor.getValue();

        System.out.println("value: " + code.value());
        System.out.println("text: " + editor.getAsText());

        // Đăng ký tường minh: phương án khác để khai báo editor.
        PropertyEditorManager.registerEditor(
                TicketCode.class, TicketCodeEditor.class);

        PropertyEditor registered =
                PropertyEditorManager.findEditor(TicketCode.class);

        System.out.println("registered: "
                + registered.getClass().getSimpleName());
    }
}
~~~

Chạy trên Linux/macOS từ thư mục gốc dự án:

~~~bash
mkdir -p out
javac -d out src/main/java/com/example/domain/TicketCode.java src/main/java/com/example/domain/TicketCodeEditor.java src/main/java/com/example/app/EditorLookupDemo.java
java -cp out com.example.app.EditorLookupDemo
~~~

Trên Windows PowerShell, tạo thư mục trước bằng:

~~~powershell
New-Item -ItemType Directory -Force out
~~~

Các lệnh `javac -d ...` và `java -cp ...` dùng tương tự khi JDK 17+ đã nằm trong PATH.

Stdout dự kiến:

~~~text
automatic: TicketCodeEditor
value: TKT-007
text: TKT-007
registered: TicketCodeEditor
~~~

Dòng `automatic` chứng minh cơ chế **tìm theo tên cùng package**, vì chưa có đăng ký tường minh ở thời điểm đầu. Dòng `registered` minh họa cơ chế đăng ký editor theo class ở bước ưu tiên cao nhất.

Các file import phù hợp và tự chứa; không cần dependency Spring. Khi thử thay tên file thành `TicketCodeConverter.java` hoặc chuyển editor sang package khác mà không cấu hình search path, `findEditor(TicketCode.class)` có thể trả `null`. Hãy **tạo một bản test riêng** khi kiểm thử trường hợp sai tên, không thay đổi mã của ví dụ chuẩn rồi coi đó là hành vi Spring mặc định.

## 4. Spring sử dụng quy ước này ở đâu?

Spring Framework có hạ tầng JavaBeans `BeanWrapperImpl` và `PropertyEditorRegistry` để đọc/ghi property và áp dụng chuyển đổi khi cần. Spring có **nhiều editor dựng sẵn** như editor cho số, locale, URL hoặc class và có thể sử dụng cơ chế tìm editor của JavaBeans cho kiểu chưa có quy tắc phù hợp.

Tuy nhiên, tồn tại các phạm vi khác nhau:

| Điểm sử dụng | Editor có thể được lấy ở đâu | Cần nhớ |
| --- | --- | --- |
| JavaBeans trực tiếp | `PropertyEditorManager.findEditor(T.class)` | Quy tắc tìm tên do JavaBeans định nghĩa |
| `BeanWrapperImpl` | Built-in editors, custom editors, hạ tầng chuyển đổi của Spring và cơ chế JavaBeans thích hợp | Có thể đăng ký editor cụ thể trên wrapper |
| `DataBinder` / `WebDataBinder` | Editor mặc định, editor đăng ký vào binder, converter/formatter được cấu hình | Phải kiểm thử trên đúng đường binding thực tế |
| `BeanFactory` / `ApplicationContext` | Built-in editors, custom editor configurer/registrar và cơ chế JavaBeans | Không đồng nghĩa mọi controller dùng một instance editor |
| `@RequestBody` JSON | Thường là `HttpMessageConverter` + Jackson | Không tự dùng `TicketCodeEditor` chỉ vì tên trùng quy ước |

Spring documentation nêu rõ việc JavaBeans phát hiện các lớp editor cùng package và có tên hậu tố `Editor`. Nhưng đừng xây dựng giả định rằng **mọi subsystem** sẽ đi qua `PropertyEditorManager` theo cùng cách. Chẳng hạn, có một `ConversionService` bean không có nghĩa toàn bộ JSON body sẽ gọi `PropertyEditor.setAsText()`.

Một hướng thiết kế ổn định: dùng quy ước này khi muốn giải thích cơ chế JavaBeans, và **đăng ký tường minh editor tại ranh giới Spring cần áp dụng** khi hành vi đó là một phần của hợp đồng ứng dụng.

## 5. Ví dụ Spring: đăng ký editor vào BeanWrapper và DataBinder

Khi cần áp dụng một editor trong một luồng binding xác định, Spring cho phép **đăng ký trực tiếp**. Cách này làm rõ nơi quy tắc được dùng và tránh phụ thuộc search path toàn JVM.

Giữ nguyên ba file Java ở mục 3, sau đó thêm file `src/main/java/com/example/app/SpringBindingDemo.java`:

~~~java
package com.example.app;

import java.util.Map;

import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

import com.example.domain.TicketCode;
import com.example.domain.TicketCodeEditor;

public final class SpringBindingDemo {

    public static final class TicketForm {
        private TicketCode code;

        public TicketCode getCode() {
            return code;
        }

        public void setCode(TicketCode code) {
            this.code = code;
        }
    }

    public static void main(String[] args) {
        TicketForm form1 = new TicketForm();
        BeanWrapper wrapper = new BeanWrapperImpl(form1);

        // Đăng ký chính xác editor cho kiểu TicketCode.
        wrapper.registerCustomEditor(
                TicketCode.class, new TicketCodeEditor());
        wrapper.setPropertyValue("code", " tkt-008 ");

        System.out.println("wrapper: " + form1.getCode().value());

        TicketForm form2 = new TicketForm();
        DataBinder binder = new DataBinder(form2, "ticketForm");

        binder.registerCustomEditor(
                TicketCode.class, new TicketCodeEditor());
        binder.setAllowedFields("code");
        binder.bind(new MutablePropertyValues(
                Map.of("code", " tkt-009 ")));

        System.out.println("binder: " + form2.getCode().value());
        System.out.println("errors: "
                + binder.getBindingResult().hasErrors());
    }
}
~~~

Tạo `settings.gradle`:

~~~groovy
rootProject.name = 'spring-editor-lookup-demo'
~~~

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.0'
}

application {
    mainClass = 'com.example.app.SpringBindingDemo'
}
~~~

Ở đây `spring-context` mang theo các module Spring cần thiết như `spring-beans`; phiên bản `6.2.0` là lựa chọn cụ thể cho ví dụ Java 17. Các project thực tế nên quản lý Spring versions thống nhất theo BOM hoặc Spring Boot dependency management để tránh trộn phiên bản.

Chạy từ thư mục gốc:

~~~bash
./gradlew run
~~~

Nếu chưa có Gradle Wrapper, dùng Gradle tương thích đã cài và lệnh `gradle run`. Trên Windows với wrapper:

~~~powershell
.\gradlew.bat run
~~~

Bỏ log của Gradle, stdout dự kiến:

~~~text
wrapper: TKT-008
binder: TKT-009
errors: false
~~~

Khác với ví dụ JavaBeans ở mục 3, lần này cả `BeanWrapper` và `DataBinder` được **đăng ký editor tường minh theo kiểu** bằng `registerCustomEditor(TicketCode.class, ...)`. Cách này không cần phụ thuộc khả năng tự phát hiện theo tên để hoàn thành binding.

### Phân biệt hai kiểu đăng ký

- `PropertyEditorManager.registerEditor(TicketCode.class, TicketCodeEditor.class)`: đăng ký **lớp editor** ở cơ chế JavaBeans và ảnh hưởng cách manager tìm editor.
- `binder.registerCustomEditor(TicketCode.class, new TicketCodeEditor())`: gắn **editor instance** cho **binder cụ thể**. Không biến editor này thành cấu hình toàn ứng dụng.

Vì `PropertyEditorSupport` có thể lưu một giá trị mutable, khi có nhiều binder độc lập nên tạo instance editor mới cho mỗi binder hoặc đăng ký qua `PropertyEditorRegistrar` tạo editor mới theo registry.

### Ghi nhận lỗi chuyển kiểu

Nếu gọi binder với `"bad"` thay `" tkt-009 "`, `TicketCode` sẽ ném `IllegalArgumentException` từ constructor. Trong luồng binding thông dụng, Spring có thể ghi `FieldError` vào `BindingResult` (thường mã cơ sở `typeMismatch`). Controller cần xử lý lỗi thân thiện, không xuất stack trace từ editor ra cho client.

Ngược lại, khi dùng `BeanWrapper.setPropertyValue(...)` trực tiếp, lỗi chuyển đổi không được tự động gói vào response HTTP; code gọi wrapper cần quyết định xử lý exception phù hợp.

Việc editor chạy thành công chỉ chứng minh có thể tạo `TicketCode` từ text; không chứng minh mã vé đó tồn tại trong database hoặc người gọi được phép xem/sửa vé.

## 6. Các cách đăng ký custom editor khác trong Spring

### 6.1. `@InitBinder`: scope của Spring MVC

Trong controller hoặc `@ControllerAdvice`, có thể khai báo:

~~~java
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

@InitBinder
public void configureBinder(WebDataBinder binder) {
    binder.registerCustomEditor(
            TicketCode.class, new TicketCodeEditor());
}
~~~

Đây là **đoạn phương thức minh họa**, cần đặt trong controller/advice hợp lệ và import `TicketCode`, `TicketCodeEditor`. `@InitBinder` áp dụng cho binding thuộc phạm vi MVC tương ứng, không phải cho mọi `@RequestBody` JSON.

Nếu một endpoint nhận `@ModelAttribute` hoặc `@RequestParam` kiểu `TicketCode`, Spring MVC có thể cần conversion theo hệ thống resolver/binder của endpoint. Luôn kiểm thử thực tế vì đường xử lý của từng loại argument và converter/formatter cấu hình khác nhau.

Đối với request form không đáng tin cậy, editor không nên quyết định caller có quyền thay đổi property nào. Sử dụng DTO rõ ràng, `setAllowedFields(...)` cho property binding và kiểm tra authorization ở tầng ứng dụng.

### 6.2. `PropertyEditorRegistrar`: gom nhiều editor

Thay vì đăng ký rải rác ở nhiều chỗ, có thể tạo một registrar dùng lại:

~~~java
import org.springframework.beans.PropertyEditorRegistrar;
import org.springframework.beans.PropertyEditorRegistry;

public final class DomainEditorRegistrar
        implements PropertyEditorRegistrar {

    @Override
    public void registerCustomEditors(PropertyEditorRegistry registry) {
        registry.registerCustomEditor(
                TicketCode.class, new TicketCodeEditor());
    }
}
~~~

Đoạn trên là **một class minh họa** cần đặt trong package phù hợp và thêm imports `TicketCode`/`TicketCodeEditor`. Điểm quan trọng: method `registerCustomEditors(...)` **tạo editor mới** cho registry được truyền vào, không dùng một instance mutable singleton. Cùng một registrar có thể được sử dụng bởi nhiều binder/bean factory nếu cấu hình tích hợp.

Một cách dùng với `DataBinder`:

~~~java
DataBinder binder = new DataBinder(target, "ticketForm");
new DomainEditorRegistrar().registerCustomEditors(binder);
~~~

Snippet cần biến `target` hợp lệ và các imports `DataBinder` tương ứng. Vì `DataBinder` triển khai `PropertyEditorRegistry`, registrar có thể đăng ký editor trực tiếp. Khi sử dụng trong container, có thể gắn registrar vào cơ chế cấu hình editor của bean factory.

### 6.3. `CustomEditorConfigurer`: đăng ký cho BeanFactory

Spring cung cấp `org.springframework.beans.factory.config.CustomEditorConfigurer`, một `BeanFactoryPostProcessor` để cấu hình custom property editors hoặc registrars cho container. Cách cấu hình mang tính minh họa:

~~~java
@Bean
public static CustomEditorConfigurer customEditorConfigurer() {
    CustomEditorConfigurer configurer = new CustomEditorConfigurer();
    configurer.setPropertyEditorRegistrars(
            new PropertyEditorRegistrar[] {
                    new DomainEditorRegistrar()
            });
    return configurer;
}
~~~

Đoạn trên phải đặt trong một class `@Configuration`; thêm imports `Bean`, `CustomEditorConfigurer`, `PropertyEditorRegistrar` và registrar tự viết. Khai báo `static @Bean` thích hợp cho BeanFactoryPostProcessor để tránh vô tình khởi tạo cấu hình quá sớm. Nó áp dụng cho đường chỉnh property của BeanFactory; **không mặc nhiên** biến thành một quy tắc cho mọi request MVC hay Jackson.

Khi chỉ cần chuẩn hóa một trường trong một controller, `@InitBinder`/converter phù hợp có thể đơn giản hơn cấu hình toàn bộ BeanFactory.

### 6.4. `BeanInfo`: khai báo editor cho một property cụ thể

JavaBeans cũng có metadata `BeanInfo`/`PropertyDescriptor`. Thay vì để manager tìm editor theo **kiểu**, một bean có thể chỉ định editor cho **một property cụ thể** bằng metadata JavaBeans, ví dụ qua `PropertyDescriptor.setPropertyEditorClass(...)` hoặc cơ chế tương ứng.

Đây là một con đường khác để chọn editor; **không nên nhầm** với tự tìm `TicketCodeEditor` dựa trên tên class `TicketCode`. Trong ứng dụng Spring hiện đại, registry hoặc type converter thường dễ kiểm tra hơn việc tạo BeanInfo tùy biến cho từng property.

## 7. Phân biệt PropertyEditor và ConversionService/Formatter

Khi học PropertyEditor, cần biết vì sao Spring có cơ chế chuyển đổi hiện đại:

| Khía cạnh | JavaBeans `PropertyEditor` | Spring `Converter<S,T>` | Spring `Formatter<T>` |
| --- | --- | --- | --- |
| Mô hình | Editor mutable, có value hiện tại; thường text ↔ object | Hàm chuyển kiểu theo cặp nguồn/đích | Parse/print có thông tin `Locale` |
| API thường dùng | `setAsText`, `getAsText`, `getValue` | `convert(source)` | `parse(text, locale)`, `print(object, locale)` |
| Đăng ký | Manager naming/registry, `@InitBinder`, registrar, configurer | `ConversionService` / `ConverterRegistry` | `FormattingConversionService` / `FormatterRegistry` |
| Phạm vi | Tùy nơi editor được tìm hoặc đăng ký | Nơi sử dụng service đó | Nơi sử dụng formatting service đó |
| Thread-safety | Tránh chia sẻ instance có trạng thái | Thường xây dựng converter stateless | Formatter nên stateless hoặc an toàn với concurrency |
| Phù hợp | Tương thích JavaBeans/legacy binding, cấu hình container | Chuyển kiểu dùng chung trong code và binder | Ngày, số, tiền tệ phụ thuộc locale |

Ví dụ `Converter<String, TicketCode>`:

~~~java
import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

public final class StringToTicketCodeConverter
        implements Converter<String, TicketCode> {

    @Override
    public TicketCode convert(String source) {
        return new TicketCode(
                source.strip().toUpperCase(Locale.ROOT));
    }
}
~~~

Đoạn này **minh họa riêng**, cần import kiểu `TicketCode`; nó không phải file chạy độc lập và chỉ có ý nghĩa khi đã đăng ký vào `ConversionService` mà luồng xử lý sử dụng. Tên `StringToTicketCodeConverter` **không** theo quy ước JavaBeans `TicketCodeEditor` và không tự được `PropertyEditorManager.findEditor(TicketCode.class)` tìm thấy.

Đối với Spring MVC hiện đại, `ConversionService` và `FormatterRegistry` thường là lựa chọn tự nhiên cho chuyển đổi kiểu và formatting; `PropertyEditor` vẫn hữu ích trong legacy JavaBeans hoặc khi cần tùy biến binding cụ thể.

**Không phải đánh đồng:** Jackson `@RequestBody` JSON, Spring `@ConfigurationProperties`, MVC form binding và BeanFactory có thể sử dụng **hệ thống chuyển đổi khác nhau**. Việc đăng ký editor theo naming convention không tự tác động lên tất cả.

## 8. Lỗi thường gặp khi lớp editor không được tìm thấy

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| `findEditor(TicketCode.class) == null` | Editor sai tên hoặc khác package | Kiểm tra fully qualified names của cả hai class |
| Editor có tên `TicketCodeConverter` | Hậu tố không phải `Editor` | Đổi tên đúng quy ước hoặc đăng ký rõ |
| Editor ở `com.example.editors` | Không cùng package, search path chưa chứa package | Dùng `getEditorSearchPath()` hoặc đăng ký rõ |
| Editor class tồn tại nhưng không tạo được instance | Constructor/accessibility/module packaging không phù hợp | Kiểm tra `public` class, constructor không đối số, module exports/opens nếu dùng JPMS |
| `setAsText(...)` không thực hiện chuyển đổi | Chưa override hoặc không gọi `setValue(...)` | Kiểm tra implementation và unit test |
| `getAsText()` cho kết quả không mong đợi | Chưa định nghĩa text format mong muốn | Override `getAsText()` và kiểm thử round-trip |
| Spring không dùng editor dù `findEditor(...)` thành công | Đường binding có conversion service/JSON handler hoặc registry khác | Test tại `BeanWrapper`/`DataBinder`/MVC thực tế |
| Cùng mã chạy khác giữa test và server | Khác classloader/module/JDK; đăng ký toàn cục bị test khác tác động | Kiểm tra runtime classpath và tránh thay manager toàn cục trong test chia sẻ |
| Input lỗi làm request thất bại | `setAsText` ném exception hợp lệ | Trả lỗi binding/validation rõ ràng, không rò stack trace |
| Editor xử lý khác nhau giữa các request | Một editor mutable dùng chung | Tạo instance mới theo registry/request/binding lifecycle |

### 8.1. Chẩn đoán theo thứ tự

1. Đọc `targetType.getName()` và `targetType.getSimpleName()` để biết Spring/JavaBeans đang xử lý kiểu nào.
2. Kiểm tra tên đầy đủ dự kiến: `com.example.domain.TicketCodeEditor`.
3. Kiểm tra editor có thật trong classpath/JAR, có accessible no-arg constructor và implements `PropertyEditor`.
4. Gọi `PropertyEditorManager.findEditor(TicketCode.class)` trong một test JDK tối thiểu, không trộn lỗi Spring.
5. Nếu editor khác package, kiểm tra `getEditorSearchPath()` nhưng ưu tiên đăng ký explicit thay vì đổi path toàn runtime.
6. Nếu JavaBeans tìm được nhưng Spring không bind, kiểm tra **đúng binder** và cơ chế conversion thực sự mà endpoint sử dụng.
7. Kiểm thử input hợp lệ, chuỗi rỗng, null, sai định dạng, nhiều request đồng thời và round-trip `setAsText/getAsText`.
8. Chọn registration scope tối thiểu đủ dùng; không sửa global manager trong code xử lý request.

### 8.2. Sai lầm khó nhận ra

**Sai lầm 1: đặt editor cùng package với controller.**  
JavaBeans tìm theo **package của kiểu dữ liệu đích**, không theo package của controller hoặc của property chứa nó.

**Sai lầm 2: đổi tên kiểu dữ liệu nhưng quên tên editor.**  
Nếu `TicketCode` đổi thành `IssueCode`, class editor cũ `TicketCodeEditor` không còn thỏa quy ước của `IssueCode`. Cần đổi tên editor hoặc đăng ký theo kiểu mới.

**Sai lầm 3: cho rằng đặt tên đúng chắc chắn luôn được mọi Spring API gọi.**  
Quy tắc của JavaBeans chỉ phát huy khi cơ chế tìm editor được sử dụng. Với JSON body, một Jackson deserializer có thể cần cấu hình riêng. Với ConversionService, cần đăng ký converter riêng.

**Sai lầm 4: chia sẻ PropertyEditorSupport singleton.**  
Editor giữ giá trị bằng `setValue/getValue`; nếu một editor instance bị sử dụng cho hai request đan xen, chúng có thể ghi đè trạng thái của nhau. Dùng registrar và tạo editor mới trong đúng lifecycle.

**Sai lầm 5: để editor xử lý cả nghiệp vụ.**  
Editor có nhiệm vụ parse/format, không nên gọi database hoặc cấp quyền cho mã vé. Việc tồn tại/phân quyền/giới hạn nghiệp vụ thuộc tầng domain/service/authorization.

## 9. Thực hành kiểm thử

Một unit test JavaBeans có thể kiểm tra trực tiếp:

~~~java
PropertyEditor editor =
        PropertyEditorManager.findEditor(TicketCode.class);

assertNotNull(editor);
editor.setAsText(" tkt-007 ");
assertEquals(new TicketCode("TKT-007"), editor.getValue());
assertEquals("TKT-007", editor.getAsText());
~~~

Đây là đoạn **JUnit minh họa**, cần import `java.beans.PropertyEditor`, `PropertyEditorManager`, kiểu `TicketCode` và static `Assertions`. Với Gradle/Maven, cần dependency JUnit; còn chương trình Java thuần ở mục 3 đã xác minh hành vi mà không cần JUnit.

Một integration test Spring nên thêm:

- Binding `TicketForm.code` từ String trong `BeanWrapperImpl` hoặc `DataBinder` sau khi đăng ký editor.
- Input sai khiến kết quả binding ghi lỗi hợp lệ, không biến giá trị sai thành một object bất kỳ.
- Hai binder dùng **hai editor instance** riêng khi xây dựng qua registrar.
- Controller thực tế nhận form/query và trả phản hồi đúng, đặc biệt khi có `ConversionService` khác.
- Không áp dụng quy tắc editor ngoài dự định lên JSON body và các loại request không thuộc phạm vi.

Khi refactor tên package hoặc kiểu dữ liệu, test `PropertyEditorManager.findEditor(...)` giúp phát hiện convention bị hỏng sớm hơn lúc một request thực tế gặp lỗi.

## 10. Checklist áp dụng và câu hỏi tự kiểm tra

**Checklist:**

- Tên class editor = **tên đơn giản của kiểu đích + `Editor`** và cùng package nếu muốn JavaBeans tự tìm bằng quy ước phổ biến.
- Class editor public, có constructor không đối số có thể truy cập, thực hiện `PropertyEditor` (thường qua `PropertyEditorSupport`).
- Kiểm thử `setAsText/getAsText`, null, input sai và thông điệp lỗi.
- Nếu editor không cùng package, chọn đăng ký explicit hoặc dùng search path có kiểm soát.
- Không nhầm `PropertyEditorManager.registerEditor` toàn cục với `PropertyEditorRegistry.registerCustomEditor` trên binder riêng.
- Không tái sử dụng editor instance mutable qua nhiều request; dùng registrar/factory tạo instance khi cần.
- Test đường xử lý thật của Spring, không suy luận MVC hoặc JSON chắc chắn dùng editor chỉ từ tên class.
- Chọn `Converter`/`Formatter` cho các tình huống type conversion mới phù hợp; dùng editor khi cần JavaBeans/legacy compatibility.
- Phân tách parsing, validation, authorization; không đưa business I/O vào editor.

**Câu hỏi:**

1. Với kiểu `com.myapp.money.Amount`, JavaBeans thử tên lớp editor cùng package nào?
2. Nếu editor đặt ở `com.myapp.editors`, cần cơ chế nào để `findEditor(Amount.class)` có thể tìm được?
3. Trong ba cách của `PropertyEditorManager`, cách nào có ưu tiên cao nhất?
4. Vì sao `AmountPropertyEditor` không tự khớp nếu kiểu là `Amount`?
5. Khác biệt giữa đăng ký class editor bằng `PropertyEditorManager.registerEditor` và một editor instance bằng `DataBinder.registerCustomEditor` là gì?
6. Khi nào nên dùng `PropertyEditorRegistrar` thay vì giữ một editor singleton?
7. Vì sao `@RequestBody` JSON có thể không dùng một `AmountEditor` dù JavaBeans tìm được?
8. Một `PropertyEditor` trả về object đúng kiểu có tự bảo đảm dữ liệu hợp lệ về nghiệp vụ không?

**Kết luận:** Quy ước tìm class editor theo tên kiểu dữ liệu là một cơ chế của **JavaBeans**: ưu tiên editor đăng ký tường minh, kế đó tìm **`<FullyQualifiedTargetType>Editor`**, cuối cùng tìm **`<SimpleTargetType>Editor`** trong các package thuộc search path. Trong Spring, đây là nền tảng hữu ích của `PropertyEditor`, nhưng muốn áp dụng ổn định cần hiểu rõ scope `BeanWrapper`/`DataBinder`/container và không đánh đồng với `ConversionService` hay Jackson.

### Tài liệu tham khảo

- Java SE 17 — `PropertyEditorManager`: https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/PropertyEditorManager.html
- Java SE 17 — `PropertyEditor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/PropertyEditor.html
- Java SE 17 — `PropertyEditorSupport`: https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/PropertyEditorSupport.html
- Spring Framework — Data Binding, PropertyEditors and Custom PropertyEditors: https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html
- Spring Framework — Type Conversion / Converter: https://docs.spring.io/spring-framework/reference/core/validation/convert.html
- Spring Framework — Field Formatting: https://docs.spring.io/spring-framework/reference/core/validation/format.html
