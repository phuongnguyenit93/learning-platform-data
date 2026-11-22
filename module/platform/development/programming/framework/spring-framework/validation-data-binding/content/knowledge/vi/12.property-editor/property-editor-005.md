# CustomNumberEditor, CustomBooleanEditor và CustomDateEditor trong Spring Data Binding

## 1. Bức tranh chung: vì sao cần ba PropertyEditor này?

Một form HTML hoặc query parameter thường gửi giá trị dưới dạng chuỗi: số lượng là **"12"**, câu trả lời bật/tắt là **"Y"**, ngày bắt đầu là **"29/02/2024"**. Nhưng DTO Java lại khai báo các kiểu **Integer**, **Boolean** và **java.util.Date**. Trước khi gán vào DTO, Spring phải hiểu chuỗi đó biểu diễn giá trị Java nào.

Ba lớp trong gói **org.springframework.beans.propertyeditors** giải quyết ba bài toán chuyển đổi quen thuộc:

- **CustomNumberEditor**: chuyển chuỗi thành một lớp con của **Number**, chẳng hạn **Integer**, **Long**, **BigDecimal**, và có thể dùng **NumberFormat** riêng.
- **CustomBooleanEditor**: chuyển các chuỗi đại diện cho đúng/sai thành **Boolean**, với quy tắc nhận diện mặc định hoặc hai chuỗi tự chọn.
- **CustomDateEditor**: chuyển chuỗi ngày thành **java.util.Date** dựa trên **DateFormat** mà ứng dụng cung cấp.

Đây là các bộ biên dịch *biểu diễn của giá trị*, không phải các annotation kiểm tra nghiệp vụ. Chúng không trả lời “đơn hàng có hợp lệ không?” hoặc “ngày này đã qua chưa?”. Chúng trả lời trước tiên: “chuỗi nhận được có chuyển thành kiểu đích theo quy tắc này được không?”.

Ví dụ mục tiêu:

~~~text
Input form                         DTO sau khi binding
--------------------------------------------------------------
quantity = "12"                 -> Integer quantity = 12
enabled  = "Y"                  -> Boolean enabled = true
startDate = "29/02/2024"        -> Date startDate = ngày 29/02/2024
~~~

Nếu dữ liệu sai kiểu như **quantity="twelve"**, **enabled="maybe"** hoặc **startDate="31/02/2025"**, binder cần báo lỗi thay vì tự bịa giá trị “gần đúng”.

**Vị trí của bài:** nhóm **PropertyEditor** trong chủ đề **Spring Framework – validation-data-binding**. Trọng tâm là cơ chế JavaBeans/Spring DataBinder, cấu hình phạm vi editor, xử lý lỗi và giới hạn khi dùng những editor truyền thống này.

## 2. Từ chuỗi đầu vào đến thuộc tính Java: cơ chế PropertyEditor

**java.beans.PropertyEditor** là giao diện có từ JavaBeans. Phương thức thường gặp gồm:

- **setAsText(String)**: nhận biểu diễn dạng văn bản; editor phân tích cú pháp và đặt giá trị Java nội bộ bằng **setValue(...)**.
- **getValue()**: trả giá trị Java hiện đang được editor giữ.
- **setValue(Object)**: đặt giá trị Java vào editor; một số implementation có thể kiểm tra hoặc điều chỉnh kiểu.
- **getAsText()**: biểu diễn giá trị đang giữ thành chuỗi; có thể hữu ích khi hiển thị dữ liệu trở lại form.

Các editor trong bài kế thừa **PropertyEditorSupport**, là lớp triển khai cơ sở do Java cung cấp. Mỗi editor có trạng thái nội bộ, vì vậy không nên dùng chung một instance editor tùy chỉnh qua nhiều luồng/request.

Ở mức khái niệm, quá trình property binding diễn ra như sau:

~~~text
HTTP form / MutablePropertyValues
          |
          v
DataBinder + BeanWrapper
          |
          +-- tìm thuộc tính cần gán
          +-- xem kiểu Java của thuộc tính
          +-- áp dụng PropertyEditor/ConversionService phù hợp
          |      |
          |      +-- setAsText("12") -> getValue() là Integer 12
          |      +-- nếu lỗi parse -> ghi nhận binding error
          |
          v
Gọi setter hoặc cơ chế truy cập đã cấu hình
          |
          v
BindingResult: lỗi chuyển kiểu, field bị chặn, v.v.
          |
          v
Validator chạy nếu ứng dụng kích hoạt riêng
~~~

Sơ đồ là mô hình để hiểu trách nhiệm. Spring còn có **ConversionService** và **Formatter**; editor tùy chỉnh được đăng ký cho kiểu/đường dẫn phù hợp sẽ tham gia quá trình chuyển đổi khi binder cần. Không mặc định mọi chuỗi ở mọi đường nhận HTTP đều đi qua cùng một editor.

Trong Spring MVC, một **WebDataBinder** gắn dữ liệu cho model attribute theo cơ chế kế thừa từ **DataBinder**. Với **@RequestBody** JSON, Jackson/HttpMessageConverter thường là nơi đọc và giải tuần tự JSON; đăng ký editor qua **@InitBinder** không tự biến đổi toàn bộ trường JSON trước Jackson.

## 3. So sánh nhanh ba editor

| Editor | Kiểu đích | Cấu hình chính | Ví dụ giá trị | Chú ý |
| --- | --- | --- | --- | --- |
| **CustomNumberEditor** | Lớp con **Number**: Integer, Long, Double, BigDecimal... | **numberClass**, **NumberFormat** tùy chọn, **allowEmpty** | "12" → Integer 12 | Chọn đúng kiểu đích và định dạng/Locale |
| **CustomBooleanEditor** | **Boolean** hoặc cách sử dụng tương ứng cho boolean | **trueString**, **falseString** tùy chọn, **allowEmpty** | "Y" → true | Phải xác định tập chuỗi được chấp nhận |
| **CustomDateEditor** | **java.util.Date** | **DateFormat**, **allowEmpty**, **exactDateLength** tùy chọn | "29/02/2024" → Date | DateFormat, múi giờ và strictness phải được kiểm soát |

Cả ba có thể nhận chuỗi rỗng thành **null** khi cấu hình **allowEmpty=true**. **null** chỉ có nghĩa khi thuộc tính đích có thể chứa null; các kiểu nguyên thủy như **int** hoặc **boolean** không biểu diễn được null. **allowEmpty=true** cũng không tự làm một trường trở thành tùy chọn theo nghiệp vụ: cần xem ràng buộc **@NotNull**, **@NotBlank**, hoặc logic miền.

Spring có sẵn các editor cho số và Boolean trong cơ chế mặc định của **BeanWrapperImpl**, nhưng ứng dụng vẫn có thể đăng ký biến thể tùy chỉnh để thay đổi định dạng hoặc phạm vi giá trị. **CustomDateEditor không được tự đăng ký mặc định** vì không có một định dạng ngày duy nhất phù hợp mọi ứng dụng; khi cần sử dụng nó, hãy đăng ký với định dạng cụ thể.

## 4. CustomNumberEditor: kiểm soát kiểu số và định dạng

Các constructor điển hình:

~~~java
new CustomNumberEditor(Integer.class, false);

new CustomNumberEditor(
        java.math.BigDecimal.class,
        java.text.NumberFormat.getNumberInstance(java.util.Locale.US),
        true);
~~~

Hai lời gọi trên là đoạn minh họa cấu hình, chưa phải chương trình độc lập.

Dạng đầu sử dụng cách phân tích số thông thường do Spring hỗ trợ; dạng sau thêm một **NumberFormat** cho văn bản theo định dạng **Locale.US**. **allowEmpty=false** không chấp nhận chuỗi rỗng thành null; **allowEmpty=true** cho phép trường hợp đó. Tên **numberClass** phải là lớp con **Number** (chẳng hạn **Integer.class**, không phải **int.class**).

Các việc CustomNumberEditor làm:

1. Nhận chuỗi được chuyển vào **setAsText(...)**.
2. Nếu rỗng và cho phép rỗng thì đặt giá trị **null**; nếu không cho phép thì báo lỗi.
3. Nếu có **NumberFormat**, dùng định dạng đó để phân tích; nếu không, dùng cơ chế parse số thông thường.
4. Chuyển/ép kết quả về lớp **Number** đã khai báo nếu phù hợp và lưu giá trị để binder gán cho thuộc tính.
5. Khi cần xuất lại văn bản, **getAsText()** có thể áp dụng **NumberFormat** đã cung cấp hoặc biểu diễn số thông thường.

Không dùng **CustomNumberEditor(Integer.class, ...)** để gắn thẳng một giá trị vào thuộc tính **BigDecimal**; kiểu editor và kiểu đích phải khớp. Với giá trị tiền, nên ưu tiên **BigDecimal** thay vì **Double** khi cần độ chính xác thập phân.

### Locale và dấu phân cách

Ví dụ **"1,234.50"** có thể có ý nghĩa khác **"1.234,50"** tùy Locale. Nếu ứng dụng cần định dạng có dấu phân cách, phải công bố Locale mong đợi và cấu hình rõ **NumberFormat**. Không nên xóa toàn bộ dấu phẩy/dấu chấm để “cứu” mọi input vì điều đó có thể làm sai giá trị.

**NumberFormat có thể phân tích linh hoạt hơn một quy tắc nhập liệu nghiêm ngặt**. Nếu API bắt buộc đúng toàn bộ chuỗi theo một mẫu định dạng, cần kiểm tra thêm cú pháp và độ dài của chuỗi đầu vào hoặc dùng parser chuyên biệt có kiểm tra toàn bộ nội dung. **CustomNumberEditor** không thay thế quy tắc kiểm tra giới hạn số, miền giá trị hay phân quyền.

## 5. CustomBooleanEditor: ánh xạ chuỗi sang Boolean

Constructor phổ biến:

~~~java
new CustomBooleanEditor(true);
new CustomBooleanEditor("Y", "N", true);
new CustomBooleanEditor("enabled", "disabled", false);
~~~

Với constructor **CustomBooleanEditor(boolean allowEmpty)**, các chuỗi được nhận diện theo quy tắc mặc định của Spring, không phân biệt hoa/thường đối với từ:

| Biểu diễn | Giá trị Boolean |
| --- | --- |
| "true", "on", "yes", "1" | true |
| "false", "off", "no", "0" | false |
| Chuỗi rỗng, allowEmpty=true | null |
| "maybe" | Không chuyển đổi được |

Khi chỉ định cả **trueString** và **falseString** như **"Y"** và **"N"**, editor sẽ ưu tiên chính các nhãn đó cho từng giá trị; không nên giả định mọi biến thể mặc định như **"yes"** còn được chấp nhận. So sánh nhãn chữ theo logic không phân biệt hoa/thường của editor. Không nên tự gộp tất cả chuỗi không hiểu được thành **false** vì dữ liệu sai sẽ bị diễn giải thành quyết định của người dùng.

**Boolean** là wrapper có ba trạng thái có thể có: **true**, **false**, **null**. **boolean** nguyên thủy chỉ có **true/false**. Một checkbox không được gửi trong form không đồng nghĩa với một giá trị **"N"** rõ ràng; **WebDataBinder** còn có cơ chế field marker cho form checkbox. Cần định nghĩa hợp đồng đầu vào và kiểm tra tình huống “không gửi”, “gửi chuỗi rỗng” và “gửi N” riêng biệt.

Nếu nghiệp vụ cần phân biệt **chưa chọn** và **đã chọn false**, dùng **Boolean** và chính sách giá trị rỗng phù hợp. Nếu bắt buộc người dùng đưa ra quyết định, một constraint như **@NotNull** có thể kiểm tra sau khi binding thành công.

## 6. CustomDateEditor: phân tích java.util.Date theo định dạng cụ thể

Các constructor:

~~~java
new CustomDateEditor(dateFormat, false);
new CustomDateEditor(dateFormat, false, 10);
~~~

Trong đó **dateFormat** là một đối tượng **java.text.DateFormat** hợp lệ, ví dụ:

~~~java
java.text.SimpleDateFormat format =
        new java.text.SimpleDateFormat(
                "dd/MM/yyyy", java.util.Locale.ROOT);

format.setLenient(false);
format.setTimeZone(java.util.TimeZone.getTimeZone("UTC"));
~~~

Đây là trích đoạn cấu hình, không phải chương trình độc lập. Với **"29/02/2024"**, lịch Gregorian chấp nhận ngày nhuận; với **"31/02/2025"**, **setLenient(false)** yêu cầu từ chối một ngày không tồn tại thay vì tự chỉnh sang tháng khác.

**allowEmpty** xử lý chuỗi rỗng thành null hay lỗi, tương tự hai editor trước. **exactDateLength=10** bổ sung kiểm tra độ dài văn bản, hữu ích vì **SimpleDateFormat** có một số cách parse không nghiêm ngặt ngay cả khi **setLenient(false)**. Tuy nhiên kiểm tra độ dài không tự bảo đảm mọi vị trí, chữ số và dấu phân cách đều khớp mẫu: nếu API yêu cầu chính xác **dd/MM/yyyy**, hãy kiểm thử định dạng chặt chẽ và cân nhắc **java.time.DateTimeFormatter** với chế độ strict cho nghiệp vụ mới.

**DateFormat/SimpleDateFormat có trạng thái và không an toàn khi chia sẻ tùy ý giữa nhiều luồng.** Trong ứng dụng web, tạo mới formatter và editor cho mỗi binder hoặc sử dụng cơ chế formatter hiện đại phù hợp. Không đặt một instance **CustomDateEditor** dùng chung như singleton cho nhiều request.

Khác biệt quan trọng: **CustomDateEditor** xử lý **java.util.Date**, tức một thời điểm (instant) được mô tả bởi số mili giây tính từ epoch. Nếu dữ liệu là **ngày lịch không có giờ/múi giờ**, kiểu miền thường phù hợp hơn là **java.time.LocalDate**. Với LocalDate, nên dùng **@DateTimeFormat** hoặc Formatter/Converter dành cho **java.time**, không đăng ký CustomDateEditor rồi mong nó tự áp dụng cho LocalDate.

## 7. Ví dụ Java 17+ đầy đủ: ba editor trong cùng DataBinder

Ví dụ này sử dụng **Java 17** và **Spring Framework 6.2.15** để tái hiện thao tác binding trên một JavaBean. Input được tạo ngay trong chương trình; không có HTTP server. Ta cố ý cấu hình các editor cho từng thuộc tính bằng **registerCustomEditor(type, propertyPath, editor)** để tránh tác động lên các thuộc tính cùng kiểu không liên quan.

Cấu trúc:

~~~text
spring-property-editor-demo/
├── pom.xml
└── src/main/java/demo/PropertyEditorsDemo.java
~~~

**pom.xml:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-property-editor-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.15</version>
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
                    <mainClass>demo.PropertyEditorsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/PropertyEditorsDemo.java:**

~~~java
package demo;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.propertyeditors.CustomBooleanEditor;
import org.springframework.beans.propertyeditors.CustomDateEditor;
import org.springframework.beans.propertyeditors.CustomNumberEditor;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public final class PropertyEditorsDemo {

    public static void main(String[] args) {
        show("OK", "12", "Y", "29/02/2024");
        show("OPTIONAL_BLANK", "12", "", "29/02/2024");
        show("INVALID", "twelve", "maybe", "31/02/2025");
    }

    private static void show(
            String label, String quantityText,
            String enabledText, String dateText) {

        RegistrationForm form = new RegistrationForm();
        DataBinder binder = new DataBinder(form, "registrationForm");

        binder.setAllowedFields("quantity", "enabled", "startDate");

        // Một editor cho Integer (số lượng là bắt buộc ở bước parse).
        binder.registerCustomEditor(
                Integer.class, "quantity",
                new CustomNumberEditor(Integer.class, false));

        // Y = true; N = false; chuỗi rỗng = null.
        binder.registerCustomEditor(
                Boolean.class, "enabled",
                new CustomBooleanEditor("Y", "N", true));

        // Tạo DateFormat mới cho từng binder, không chia sẻ giữa request.
        SimpleDateFormat inputFormat =
                new SimpleDateFormat("dd/MM/yyyy", Locale.ROOT);
        inputFormat.setLenient(false);
        inputFormat.setTimeZone(TimeZone.getTimeZone("UTC"));

        binder.registerCustomEditor(
                Date.class, "startDate",
                new CustomDateEditor(inputFormat, false, 10));

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("quantity", quantityText);
        values.add("enabled", enabledText);
        values.add("startDate", dateText);

        binder.bind(values);
        BindingResult errors = binder.getBindingResult();

        SimpleDateFormat outputFormat =
                new SimpleDateFormat("yyyy-MM-dd", Locale.ROOT);
        outputFormat.setTimeZone(TimeZone.getTimeZone("UTC"));

        String date = form.getStartDate() == null
                ? "null"
                : outputFormat.format(form.getStartDate());

        System.out.println("[" + label + "]");
        System.out.println("quantity=" + form.getQuantity());
        System.out.println("enabled=" + form.getEnabled());
        System.out.println("startDate=" + date);
        System.out.println("hasErrors=" + errors.hasErrors());

        if (errors.hasErrors()) {
            System.out.println(
                    "quantity.error=" + errors.hasFieldErrors("quantity"));
            System.out.println(
                    "enabled.error=" + errors.hasFieldErrors("enabled"));
            System.out.println(
                    "startDate.error=" + errors.hasFieldErrors("startDate"));
        }
    }

    public static final class RegistrationForm {
        private Integer quantity;
        private Boolean enabled;
        private Date startDate;

        public RegistrationForm() {
        }

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }

        public Boolean getEnabled() {
            return enabled;
        }

        public void setEnabled(Boolean enabled) {
            this.enabled = enabled;
        }

        public Date getStartDate() {
            return startDate;
        }

        public void setStartDate(Date startDate) {
            this.startDate = startDate;
        }
    }
}
~~~

Chạy trong thư mục chứa **pom.xml**:

~~~bash
mvn -q compile exec:java
~~~

Cần JDK 17+ và Maven; lần đầu cần truy cập Maven Central. Kết quả chương trình dự kiến (không tính log Maven):

~~~text
[OK]
quantity=12
enabled=true
startDate=2024-02-29
hasErrors=false
[OPTIONAL_BLANK]
quantity=12
enabled=null
startDate=2024-02-29
hasErrors=false
[INVALID]
quantity=null
enabled=null
startDate=null
hasErrors=true
quantity.error=true
enabled.error=true
startDate.error=true
~~~

### Giải thích từng trường hợp

**OK:** **"12"** chuyển thành **Integer 12**; **"Y"** thành **Boolean.TRUE**; **"29/02/2024"** thành Date hợp lệ. Khi in, chương trình dùng UTC và định dạng **yyyy-MM-dd**, vì thế đầu ra ngày không phụ thuộc múi giờ mặc định của máy. **BindingResult** không có lỗi.

**OPTIONAL_BLANK:** cùng số/ngày hợp lệ, riêng **enabled** là chuỗi rỗng. **CustomBooleanEditor("Y","N",true)** hiểu là **null** nên **hasErrors=false**. Nếu nghiệp vụ bắt buộc phải chọn, cần validator hoặc constraint phù hợp để từ chối null sau bước binding.

**INVALID:** ba chuỗi đều không hợp lệ theo quy tắc đã cấu hình: **"twelve"** không thành Integer; **"maybe"** không nằm trong tập Y/N; **31/02/2025** là ngày không tồn tại và bị từ chối bởi formatter không lenient. Binder ghi lỗi thuộc tính; các field của DTO mới tạo vẫn mang giá trị mặc định null. Không nên “sửa hộ” dữ liệu sai thành một giá trị tưởng chừng hợp lệ.

Ví dụ dùng **setAllowedFields(...)** để chỉ cho phép ba thuộc tính nhận input. Việc chỉ cho phép những trường được công bố là quan trọng ngay cả khi editor có thể chuyển được nhiều kiểu: chuyển đổi thành công không đồng nghĩa người dùng được phép sửa mọi property.

### Nếu một trường không chuyển đổi được, nhận diện lỗi thế nào?

~~~java
for (org.springframework.validation.FieldError error
        : errors.getFieldErrors()) {
    System.out.println(error.getField()
            + ": bindingFailure=" + error.isBindingFailure());
}
~~~

Đoạn này **phụ thuộc biến errors trong ví dụ chính**, không chạy độc lập. Với lỗi conversion do DataBinder ghi, **FieldError.isBindingFailure()** cho biết lỗi tại giai đoạn binding. **@Valid**, **@NotNull**, **@Min** hoặc các constraint khác cần được kích hoạt riêng; một **FieldError** do chuyển kiểu không phải mặc nhiên là lỗi Bean Validation.

## 8. Đăng ký trong Spring MVC bằng @InitBinder

Trong controller nhận **@ModelAttribute("registrationForm")**, có thể đăng ký editor trước khi Spring bind request:

~~~java
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

import org.springframework.beans.propertyeditors.CustomBooleanEditor;
import org.springframework.beans.propertyeditors.CustomDateEditor;
import org.springframework.beans.propertyeditors.CustomNumberEditor;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

// Đặt method này trong @Controller hoặc @ControllerAdvice phù hợp:
@InitBinder("registrationForm")
public void configureRegistration(WebDataBinder binder) {
    binder.registerCustomEditor(
            Integer.class, "quantity",
            new CustomNumberEditor(Integer.class, false));

    binder.registerCustomEditor(
            Boolean.class, "enabled",
            new CustomBooleanEditor("Y", "N", true));

    SimpleDateFormat dateFormat =
            new SimpleDateFormat("dd/MM/yyyy", Locale.ROOT);
    dateFormat.setLenient(false);
    dateFormat.setTimeZone(TimeZone.getTimeZone("UTC"));

    binder.registerCustomEditor(
            Date.class, "startDate",
            new CustomDateEditor(dateFormat, false, 10));

    binder.setAllowedFields("quantity", "enabled", "startDate");
}
~~~

Đoạn **@InitBinder** là mã tích hợp vào Spring MVC, cần đặt trong class controller hoặc advice phù hợp; tự nó không phải chương trình có **main**. Tên **registrationForm** cần khớp tên model attribute. Trong MVC, WebDataBinder thường được tạo cho mỗi quá trình binding nên ta tạo DateFormat/editor mới trong method này, tránh giữ một đối tượng SimpleDateFormat dùng chung.

Ví dụ controller tiêu thụ form:

~~~java
@PostMapping("/registration")
public String save(
        @Valid @ModelAttribute("registrationForm")
        RegistrationForm input,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "registration-form";
    }
    return "registration-success";
}
~~~

Đây cũng là đoạn tích hợp, cần thêm annotation import, class DTO, validation provider, view tương ứng và những constraint thực sự muốn kiểm tra. **BindingResult** phải đứng ngay sau đối số **@ModelAttribute** mà nó mô tả. Nếu input sai kiểu, lỗi thường có mã **typeMismatch**; nếu chuyển kiểu thành công nhưng không đạt ràng buộc, Bean Validation (khi được kích hoạt) tạo lỗi constraint riêng.

**Đăng ký theo field hay theo type?**

- **registerCustomEditor(Integer.class, "quantity", editor)**: phạm vi cụ thể cho **quantity**.
- **registerCustomEditor(Integer.class, editor)**: áp dụng theo kiểu **Integer** trong phạm vi binder, rộng hơn.
- **registerCustomEditor(Date.class, "startDate", editor)**: bảo đảm định dạng ngày dành riêng cho **startDate** mà không mặc định ép mọi Date vào cùng một mẫu.

Ưu tiên phạm vi hẹp khi các thuộc tính cùng kiểu có quy ước nhập khác nhau; đồng thời tránh editor này âm thầm ảnh hưởng các form/model khác.

## 9. Phân biệt PropertyEditor với ConversionService, Formatter và JSON

| Bài toán | Cơ chế nên xem xét | Vì sao |
| --- | --- | --- |
| Chuyển form String → Integer/Boolean/Date theo quy tắc kế thừa | **CustomNumberEditor**, **CustomBooleanEditor**, **CustomDateEditor** | Đúng vai trò của các PropertyEditor JavaBeans |
| Chuyển kiểu miền tự định nghĩa ở nhiều tầng ứng dụng | **Converter<S,T>** trong **ConversionService** | Có thể tái sử dụng quy tắc đổi kiểu không phụ thuộc trạng thái editor |
| Hiển thị/phân tích số, ngày theo Locale trong UI | **Formatter<T>**, Spring **FormattingConversionService** | Mô hình formatting hai chiều theo ngữ cảnh vùng miền |
| DTO dùng LocalDate, LocalDateTime | **@DateTimeFormat**, Formatter/Converter dành cho **java.time** | Các kiểu thời gian hiện đại không phải java.util.Date |
| JSON @RequestBody | **Jackson** qua **HttpMessageConverter** | JSON được đọc/giải tuần tự trước khi validation; @InitBinder không phải deserializer của JSON |
| Kiểm tra giá trị sau chuyển đổi | **Bean Validation**, **Validator** | Những ràng buộc như tuổi tối thiểu, định dạng miền, khoảng ngày hợp lệ |

Không có quy tắc “chỉ dùng PropertyEditor” hoặc “phải bỏ PropertyEditor”. Với code hiện đại, **Converter/Formatter** thường thuận tiện hơn cho những chuyển đổi cần tái sử dụng và định dạng theo Locale; editor vẫn hữu ích để hiểu hệ thống cũ và một số cấu hình đặc thù trong DataBinder.

### Lưu ý về độ an toàn của định dạng

- **NumberFormat** không phải validator đảm bảo chuỗi chỉ gồm đúng những ký tự đã công bố; cần kiểm tra độ chặt nếu hợp đồng nhập liệu yêu cầu.
- **SimpleDateFormat** không an toàn khi chia sẻ mutable instance giữa nhiều luồng. Tạo mới theo binder hoặc chuyển sang API thời gian hiện đại phù hợp.
- **Exact date length** chỉ là một phép kiểm tra thêm; không thay thế **setLenient(false)** hay một parser strict hoàn chỉnh.
- Các giá trị **null**, **""**, chuỗi toàn khoảng trắng, *field không được gửi* có thể mang ý nghĩa nghiệp vụ khác nhau.
- Việc nhận **"Y"/"N"** có thể phù hợp với form cũ nhưng không tự áp dụng đúng cho JSON boolean theo chuẩn JSON.
- Tránh ghi raw input nhạy cảm vào log hoặc trả nguyên văn parser exception ra client. API nên dùng mã lỗi dễ hiểu và thông báo hợp đồng.

## 10. Cách kiểm tra và xử lý lỗi conversion

Khi form không bind được, hỏi theo trình tự:

1. **Kiểu thuộc tính Java là gì?** Integer hay int, Boolean hay boolean, Date hay LocalDate?
2. **Dữ liệu thực tế là gì?** Query/form gửi "12", "Y", "29/02/2024" hay kiểu biểu diễn khác?
3. **Editor nào đã được đăng ký, phạm vi nào?** Theo type hay theo property path? Method **@InitBinder** có áp dụng cho model attribute đúng tên không?
4. **allowEmpty có phù hợp không?** Chuỗi rỗng được đổi thành null hay bị báo sai?
5. **Formatter có Locale/TimeZone/lenient đúng không?** Ngày nhuận, ngày không tồn tại, thứ tự ngày/tháng, dấu phân cách có khớp?
6. **BindingResult ghi lỗi gì?** Kiểm tra **hasErrors()**, **getFieldErrors("field")**, **FieldError.isBindingFailure()** và mã **typeMismatch** khi có.
7. **Validation đã chạy chưa?** Conversion thành công chưa bảo đảm ràng buộc như **@Min(1)** hoặc **@NotNull** đã được kiểm tra.

Một API có thể trả lỗi có cấu trúc như sau (JSON minh họa, không phải đầu ra mặc định của ví dụ Java):

~~~json
{
  "code": "TYPE_MISMATCH",
  "field": "startDate",
  "message": "Ngày phải có dạng dd/MM/yyyy và là ngày hợp lệ."
}
~~~

Khi form có nhiều lỗi, nên thu thập các lỗi từng field và báo riêng theo vị trí nhập; đừng biến mọi lỗi thành thông báo mơ hồ như “Dữ liệu sai”. Nhưng cũng đừng hiển thị stack trace hay chi tiết parser nội bộ không phù hợp cho người dùng cuối.

## 11. Lỗi hiểu sai phổ biến

1. **CustomNumberEditor là validator số.** Không đúng: nó chủ yếu phân tích/chuyển biểu diễn. Giới hạn nghiệp vụ như số lượng lớn hơn 0 vẫn cần ràng buộc riêng.
2. **CustomBooleanEditor chỉ nhận "true"/"false".** Không đúng với mặc định của Spring; và ứng dụng còn có thể định nghĩa nhãn riêng như Y/N.
3. **Chuỗi lạ tự trở thành false.** Không đúng: dữ liệu không khớp tập giá trị được chấp nhận phải gây lỗi conversion.
4. **allowEmpty=true bảo đảm trường hợp lệ.** Không đúng: nó cho phép null; nghiệp vụ có thể vẫn yêu cầu giá trị.
5. **CustomDateEditor chấp nhận mọi ngày có cùng độ dài.** Không đúng: cần DateFormat, kiểm tra ngày hợp lệ và chế độ parse.
6. **Chỉ setLenient(false) là đã ràng buộc chính xác mọi ký tự format.** Không đúng: SimpleDateFormat còn những đặc điểm parse cần kiểm tra bổ sung.
7. **Một DateFormat có thể lưu singleton rồi dùng cho mọi request.** Không an toàn đối với SimpleDateFormat có trạng thái.
8. **CustomDateEditor tự áp dụng cho LocalDate.** Không đúng: nó phục vụ java.util.Date, còn LocalDate có cơ chế chuyển đổi khác.
9. **@InitBinder chắc chắn chuyển đổi @RequestBody JSON.** Không đúng: JSON thông thường đi qua Jackson/HttpMessageConverter.
10. **Đăng ký editor theo type không ảnh hưởng field khác.** Có thể ảnh hưởng mọi thuộc tính cùng kiểu trong binder; dùng property path nếu cần định dạng riêng.
11. **Không có lỗi binding thì không cần validation.** Không đúng: giá trị chuyển kiểu đúng vẫn có thể sai nghiệp vụ.
12. **Chuyển được giá trị nghĩa là client có quyền ghi property đó.** Không đúng: cần DTO đầu vào, giới hạn thuộc tính và kiểm tra quyền cập nhật.

## 12. Bài tập thực hành

**Bài tập 1 — Boolean theo giao thức khác.** Đổi editor thành **CustomBooleanEditor("enabled","disabled",false)**. Thử gửi **"enabled"**, **"disabled"**, **""**, **"Y"**. Phân loại các trường hợp thành giá trị true/false hay lỗi parse. Giải thích ảnh hưởng của **allowEmpty=false**.

**Bài tập 2 — Số theo Locale.** Thêm **BigDecimal amount** vào DTO và đăng ký **CustomNumberEditor(BigDecimal.class, numberFormat, true)** với NumberFormat cụ thể. So sánh input dạng dấu phẩy và dấu chấm. Xác định cách kiểm tra chặt toàn bộ chuỗi nếu định dạng API bắt buộc.

**Bài tập 3 — Ngày nhuận.** Dùng cấu hình date editor ở mục 7, thử **29/02/2024**, **29/02/2025**, **31/04/2025** và **01/01/2025**. Giải thích tại sao **setLenient(false)** quan trọng.

**Bài tập 4 — Đổi từ Date sang LocalDate.** Thay field **startDate** thành **LocalDate**. Giải thích vì sao cần **@DateTimeFormat** hoặc formatter riêng cho LocalDate, thay vì giữ nguyên editor Date.

**Bài tập 5 — BindingResult.** Với input sai đồng thời cả ba trường, trích xuất tên field, mã lỗi và **isBindingFailure()**. Thiết kế JSON lỗi gồm danh sách từng trường mà không lộ raw input nhạy cảm.

## 13. Tài liệu tham khảo

- [Spring Framework – Data Binding và PropertyEditors](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html).
- [CustomNumberEditor – Spring Framework Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/beans/propertyeditors/CustomNumberEditor.html).
- [CustomBooleanEditor – Spring Framework Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0-M4/javadoc-api/org/springframework/beans/propertyeditors/CustomBooleanEditor.html).
- [CustomDateEditor – Spring Framework Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/beans/propertyeditors/CustomDateEditor.html).
- [Web MVC – @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html).
- [ConversionService và Spring Formatter](https://docs.spring.io/spring-framework/reference/core/validation/convert.html).

**Quy tắc thực hành:** xác định đúng kiểu Java đích, định dạng và khả năng chấp nhận giá trị rỗng; đăng ký editor trong phạm vi cần thiết; đọc lỗi qua BindingResult; sau đó mới áp dụng validation và quyền sửa dữ liệu. CustomNumberEditor, CustomBooleanEditor và CustomDateEditor giúp Spring hiểu cách biểu diễn đầu vào, không thay thế các quy tắc nghiệp vụ.