# Chuẩn hóa dữ liệu trước khi chuyển đổi trong Spring Data Binding

## 1. Vị trí của bước chuẩn hóa trong luồng xử lý

Khi nhận dữ liệu từ HTTP request, Spring MVC phải biến biểu diễn bên ngoài (thường là chuỗi ký tự từ query string hoặc form) thành kiểu Java và gán vào đối tượng đích. Trước khi đổi kiểu, đôi khi cần **chuẩn hóa** (normalization): đưa các cách biểu diễn tương đương về một quy ước đã xác định, nhưng không tự ý sửa ý nghĩa dữ liệu.

Luồng tư duy với tham số form/query là:

~~~text
HTTP request
  → đọc giá trị thô (raw values)
  → chuẩn hóa có chọn lọc theo từng trường
  → chuyển đổi kiểu (String → Integer, LocalDate, enum, ...)
  → gán thuộc tính / thu thập lỗi binding
  → Bean Validation (khi được kích hoạt)
  → controller xử lý hoặc trả lỗi
~~~

Đây là **thứ tự mong muốn khi tự thiết kế một bước tiền xử lý**, không phải lời khẳng định Spring MVC mặc định luôn chạy một bộ chuẩn hóa riêng. Theo cơ chế mặc định, **WebDataBinder/DataBinder** xử lý gán dữ liệu và gọi các bộ chuyển đổi/PropertyEditor khi cần; việc chuẩn hóa phải được cấu hình trong cơ chế đó hoặc thực hiện ở ranh giới đầu vào trước lúc gọi bind.

Phân biệt bốn hoạt động:

| Hoạt động | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Chuẩn hóa | Giảm khác biệt hình thức theo quy tắc đã chọn | "  Mai   Anh  " → "Mai Anh" |
| Chuyển đổi kiểu | Đưa giá trị về kiểu Java đích | "27" → Integer 27 |
| Kiểm tra hợp lệ | Đánh giá dữ liệu theo ràng buộc nghiệp vụ | Tuổi phải từ 18 trở lên |
| Mã hóa khi xuất | Phù hợp ngữ cảnh HTML, SQL, URL… | Escape dữ liệu khi render HTML; dùng tham số truy vấn SQL |

Không dùng thao tác chuẩn hóa để thay thế validation hay biện pháp bảo mật đầu ra.

## 2. Vì sao chuẩn hóa cần diễn ra đúng thời điểm?

Giả sử form gửi fullName = "  Mai   Anh  " và age = " 27 ". Nếu quy tắc hệ thống cho phép, có thể rút khoảng trắng tên thành "Mai Anh" và bỏ khoảng trắng bao quanh tuổi thành "27" trước khi Integer converter xử lý. Bước đổi kiểu nhận đầu vào dễ dự đoán hơn; kiểm tra dữ liệu diễn ra trên biểu diễn nhất quán.

Ngược lại, đầu vào age = "27x" phải được giữ là không hợp lệ. Không được tùy tiện xóa chữ "x" để tạo ra số 27 vì điều đó che giấu lỗi và có thể thay đổi ý định của người gửi.

**Chuẩn hóa không phải lúc nào cũng đúng với mọi trường.** Mật khẩu, token, chữ ký điện tử, mã phân biệt hoa/thường, dữ liệu cần giữ nguyên ký tự hoặc văn bản pháp lý thường không được trim, gộp khoảng trắng hay chuyển chữ hoa/thường. Chuẩn hóa phải dựa trên hợp đồng dữ liệu của từng trường.

## 3. Spring MVC thực hiện binding ở những nhánh nào?

| Nguồn đầu vào | Cơ chế chính | Điểm cần chú ý |
| --- | --- | --- |
| Form/query vào **@ModelAttribute** | Spring tạo hoặc lấy đối tượng, **WebDataBinder** bind thuộc tính, chuyển kiểu rồi có thể validate | Có thể cấu hình **@InitBinder**, PropertyEditor, Converter/Formatter; bước tiền xử lý thô riêng cần được thực hiện trước khi bind |
| Giá trị **@RequestParam** và **@PathVariable** | Bộ phân giải tham số dùng cơ chế chuyển đổi kiểu của Spring | Không mặc định đi qua một hàm chuẩn hóa chung dành riêng cho form object |
| JSON vào **@RequestBody** | **HttpMessageConverter** (thường là Jackson) đọc và giải tuần tự JSON thành object, sau đó có thể validate | **@InitBinder** không tự động trim các chuỗi bên trong JSON trước khi Jackson chuyển kiểu |
| Dữ liệu được ứng dụng tự bind | Ứng dụng tạo **DataBinder** và gọi **bind(...)** | Có thể chuẩn hóa một bản sao **MutablePropertyValues** trước lệnh bind; ví dụ đầy đủ ở phần 5 |

Trong nhánh **@ModelAttribute**, Spring thu thập lỗi chuyển đổi như lỗi **typeMismatch** trong **BindingResult**; các ràng buộc như **@NotBlank**, **@NotNull**, **@Min** chỉ chạy khi validation tương ứng được kích hoạt (chẳng hạn bằng **@Valid** và một validator phù hợp). Thất bại chuyển kiểu và thất bại validation là hai nhóm lỗi khác nhau.

## 4. Thiết kế quy tắc chuẩn hóa theo từng trường

Một chính sách an toàn có thể gồm các trường hợp sau:

- **Tên hiển thị:** bỏ khoảng trắng đầu/cuối, gộp các khoảng trắng bên trong theo chính sách sản phẩm; nếu cần xử lý Unicode, có thể chuẩn hóa dạng **NFC** để chuỗi có dấu tổ hợp và dấu dựng sẵn được biểu diễn nhất quán.
- **Số tuổi:** chỉ bỏ khoảng trắng bao quanh nếu hợp đồng chấp nhận; để bộ chuyển đổi số quyết định chuỗi có hợp lệ hay không.
- **Email:** có thể trim theo quy tắc đầu vào; không tự coi mọi phần của địa chỉ là không phân biệt hoa/thường hay sửa nội dung mà chưa có quy định.
- **Số tiền/ngày giờ:** xem xét **Locale** và định dạng đã công bố; dùng **Formatter** hay bộ phân tích có quy tắc, thay vì tự thay mọi dấu phẩy bằng dấu chấm hoặc xóa dấu phân tách.
- **Mã định danh, số điện thoại:** giữ số 0 đầu, dấu cộng và biểu diễn có ý nghĩa; không đổi thành số nguyên chỉ vì ký tự trông giống chữ số.
- **Mật khẩu, token, chữ ký, dữ liệu nhị phân:** giữ nguyên trừ khi giao thức quy định rõ khác đi.

Chốt rõ chính sách giá trị rỗng: chuỗi rỗng **""**, chuỗi chỉ có khoảng trắng và **null** có phải cùng một trạng thái hay không? Với **StringTrimmerEditor(true)**, một chuỗi đã trim thành rỗng sẽ được đổi thành **null**. Quyết định này ảnh hưởng đến validation, cập nhật từng phần và ý nghĩa “người dùng xóa giá trị”.

Các tính chất nên kiểm tra: quy tắc có thể dự đoán được; chỉ tác động trường được phép; áp dụng hai lần vẫn cho cùng kết quả (tính lũy đẳng); không “sửa hộ” dữ liệu sai; kết quả có thể truy vết mà không ghi lộ dữ liệu nhạy cảm.

## 5. Ví dụ chạy được: chuẩn hóa rồi mới gọi DataBinder.bind

Ví dụ độc lập sau dùng **Java 17+** và **Spring Framework 6.1.14**, minh họa chính xác thứ tự: lấy dữ liệu thô → tạo bản giá trị đã chuẩn hóa → gọi **DataBinder.bind(...)** → xem đối tượng và lỗi binding. Đây là cách dùng **DataBinder** khi ứng dụng **tự kiểm soát thao tác bind**; không có nghĩa một controller Spring MVC mặc định tự chạy hàm **normalize(...)** này.

Cấu trúc:

~~~text
normalize-before-bind/
├── pom.xml
└── src/main/java/demo/NormalizeBeforeBindDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>normalize-before-bind</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
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
                    <mainClass>demo.NormalizeBeforeBindDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/NormalizeBeforeBindDemo.java**:

~~~java
package demo;

import java.text.Normalizer;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.PropertyValue;
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public final class NormalizeBeforeBindDemo {

    public static void main(String[] args) {
        Registration registration = new Registration();
        DataBinder binder = new DataBinder(registration, "registration");
        binder.setAllowedFields("fullName", "age");
        binder.setConversionService(new DefaultConversionService());

        MutablePropertyValues raw = new MutablePropertyValues();
        raw.add("fullName", "  Mai\t  Anh  ");
        raw.add("age", " 27 ");

        MutablePropertyValues prepared = normalize(raw);
        binder.bind(prepared);
        BindingResult result = binder.getBindingResult();

        System.out.println("fullName = " + registration.getFullName());
        System.out.println("age = " + registration.getAge());
        System.out.println("bindingErrors = " + result.getErrorCount());
    }

    private static MutablePropertyValues normalize(MutablePropertyValues raw) {
        MutablePropertyValues prepared = new MutablePropertyValues();
        for (PropertyValue property : raw.getPropertyValues()) {
            Object value = property.getValue();

            if ("fullName".equals(property.getName()) && value instanceof String name) {
                String cleaned = name.strip().replaceAll("(?U)\\s+", " ");
                value = Normalizer.normalize(cleaned, Normalizer.Form.NFC);
            } else if ("age".equals(property.getName()) && value instanceof String ageText) {
                value = ageText.strip();
            }

            prepared.add(property.getName(), value);
        }
        return prepared;
    }

    public static final class Registration {
        private String fullName;
        private Integer age;

        public String getFullName() {
            return fullName;
        }

        public void setFullName(String fullName) {
            this.fullName = fullName;
        }

        public Integer getAge() {
            return age;
        }

        public void setAge(Integer age) {
            this.age = age;
        }
    }
}
~~~

Trong thư mục chứa **pom.xml**, chạy:

~~~bash
mvn -q compile exec:java
~~~

Đầu ra dự kiến:

~~~text
fullName = Mai Anh
age = 27
bindingErrors = 0
~~~

Giải thích: **normalize(...)** duyệt các giá trị nguồn, áp dụng quy tắc theo đúng tên trường rồi tạo **MutablePropertyValues** mới. Với **fullName**, **strip()** loại khoảng trắng đầu/cuối, biểu thức **(?U)\\s+** gộp các khoảng trắng Unicode liên tiếp và **Normalizer.Form.NFC** chuẩn hóa cách biểu diễn Unicode. Với **age**, chỉ bỏ khoảng trắng bao quanh; **DefaultConversionService** mới chuyển chuỗi "27" thành **Integer**. **setAllowedFields(...)** giới hạn những thuộc tính có thể được gán, tránh nhận tùy tiện thuộc tính khác từ dữ liệu đầu vào.

Thử thay giá trị age bằng **"27x"**: hàm chuẩn hóa không được xóa chữ x; bộ chuyển đổi số sẽ thất bại, Spring ghi lỗi binding cho trường age (thường mang mã **typeMismatch**). Ví dụ không gọi **binder.validate()**, vì vậy **bindingErrors** chỉ phản ánh kết quả bind/chuyển kiểu; nó chưa phải minh chứng rằng các điều kiện nghiệp vụ đã được kiểm tra.

## 6. Áp dụng trong Spring MVC thực tế

### 6.1. Dùng @InitBinder khi mục tiêu là trim một trường String

Trong controller hoặc một **@ControllerAdvice** phù hợp, có thể đăng ký editor cho riêng thuộc tính chuỗi:

~~~java
import org.springframework.beans.propertyeditors.StringTrimmerEditor;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.InitBinder;

@ControllerAdvice
public class RegistrationBindingAdvice {
    @InitBinder("registration")
    public void initRegistrationBinder(WebDataBinder binder) {
        binder.registerCustomEditor(
                String.class,
                "fullName",
                new StringTrimmerEditor(true));
    }
}
~~~

Đây là **đoạn cấu hình cần nằm trong ứng dụng Spring MVC**, không phải chương trình có **main** độc lập. Binder của model attribute có tên **registration** sẽ dùng editor để trim **fullName**; chuỗi chỉ gồm khoảng trắng trở thành **null**. Không suy rộng việc này cho mọi trường số hoặc mọi JSON body: **StringTrimmerEditor** là editor cho đích **String**, và nó tham gia **quá trình chuyển đổi/binding** chứ không phải một bộ tiền xử lý dữ liệu thô đứng trước tất cả converter.

Nếu nhiều controller dùng chung cấu hình, cân nhắc phạm vi của **@ControllerAdvice** và tên binder trong **@InitBinder**. Đăng ký editor cho toàn bộ **String.class** không có đường dẫn thuộc tính sẽ rộng hơn đáng kể, có thể vô tình biến đổi các trường cần giữ nguyên như password hoặc mã token.

### 6.2. Khi chuyển đổi sang kiểu miền, dùng Converter hoặc Formatter

Với một kiểu đích riêng (ví dụ mã sản phẩm được phép viết khoảng trắng đầu/cuối theo hợp đồng), có thể triển khai **Converter<String, ProductCode>** và đăng ký vào **ConversionService**. Converter có thể xử lý quy tắc chuẩn hóa cần thiết **bên trong lần chuyển đổi của kiểu đó**; đừng mô tả nó là một bước chuẩn hóa chung được Spring tự chạy trước mọi Converter khác.

Với ngày, số thập phân hoặc đơn vị phụ thuộc **Locale**, thường thích hợp hơn khi dùng **Formatter**/**Parser** có quy ước nhập rõ ràng. Tránh biến chuỗi không hợp lệ thành giá trị có vẻ hợp lệ chỉ để không gặp lỗi binding.

### 6.3. @RequestBody đi theo luồng khác

Khi controller nhận **@RequestBody**, JSON thường được Jackson giải tuần tự thông qua **HttpMessageConverter** trước lúc validation. Nếu phải chuẩn hóa một trường JSON, cần cân nhắc chính sách trong DTO, bộ giải tuần tự chuyên biệt hoặc lớp xử lý ứng dụng. **@InitBinder** không phải cơ chế tiền xử lý phổ quát cho các chuỗi trước Jackson. Nếu JSON chứa kiểu sai, lỗi có thể phát sinh ngay tại bước đọc body, trước Bean Validation.

## 7. Kiểm tra lỗi và xác nhận hành vi

Với **@ModelAttribute**, đặt **BindingResult** ngay sau tham số model nếu muốn controller tự xử lý lỗi binding/validation:

~~~java
@PostMapping("/register")
public String register(
        @Valid @ModelAttribute("registration") RegistrationForm form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "register-form";
    }
    return "register-success";
}
~~~

Đoạn này giả định đã có **RegistrationForm**, thư viện Jakarta Validation, một validator được cấu hình và hai view tương ứng. **@Valid** kích hoạt validation sau binding; nếu tuổi không đổi được sang số thì đó vẫn là lỗi binding. Với JSON **@RequestBody**, lỗi đọc JSON và lỗi Bean Validation thường đi qua nhánh xử lý exception khác; không mặc định có cùng cách trả lỗi như form.

Bộ kiểm tra tối thiểu nên bao gồm:

| Đầu vào | Kỳ vọng | Mục đích |
| --- | --- | --- |
| fullName = "  Mai   Anh  " | "Mai Anh" | Trim và gộp khoảng trắng theo chính sách |
| fullName chỉ có khoảng trắng | "" hoặc null theo hợp đồng đã chọn | Kiểm tra ranh giới empty/null và validation |
| age = " 27 " | Integer 27 | Chuẩn hóa diễn ra trước chuyển số |
| age = "27x" | Lỗi chuyển kiểu, không biến thành 27 | Không sửa hộ dữ liệu sai |
| age là số dùng dấu phân tách theo Locale khác | Chấp nhận/từ chối theo định dạng được công bố | Không đoán dấu thập phân |
| password có khoảng trắng đầu/cuối | Giữ nguyên | Tránh chuẩn hóa sai trường nhạy cảm |
| fullName đã chuẩn hóa | Không đổi khi chuẩn hóa lần hai | Tính lũy đẳng |
| JSON @RequestBody và form @ModelAttribute cùng tên trường | Hành vi phù hợp từng nhánh đọc dữ liệu | Không giả định hai cơ chế chung một pipeline |

Để kiểm tra ứng dụng thật, dùng **MockMvc** gửi form với khoảng trắng và chuỗi sai kiểu, so sánh DTO sau bind cùng **BindingResult**. Thử JSON riêng qua endpoint **@RequestBody** để kiểm tra đúng cơ chế deserialize. Nếu dùng **@NotBlank**, **@NotNull** hoặc constraint miền, thêm cả trường hợp xác nhận validator thực sự được gọi.

## 8. Lỗi phổ biến và nguyên tắc chốt

1. **Trim mọi trường**: thay đổi mật khẩu, mã phân biệt hoa/thường hoặc dữ liệu nguyên bản. Giải pháp: danh sách trường được phép chuẩn hóa.
2. **Nhầm chuẩn hóa với chuyển kiểu**: StringTrimmerEditor cho String không bảo đảm làm sạch toàn bộ đầu vào Integer/LocalDate. Giải pháp: xác định chính xác vị trí áp dụng chính sách và kiểu đích.
3. **Sửa dữ liệu sai thành dữ liệu đúng giả tạo**: xóa ký tự ngoài mong muốn trong số, tự đoán Locale, đổi định dạng ngày tùy tiện. Giải pháp: trả lỗi minh bạch khi đầu vào không đạt hợp đồng.
4. **Nhầm @ModelAttribute với @RequestBody**: một @InitBinder không có nghĩa chỉnh JSON trước Jackson. Giải pháp: kiểm tra đúng nhánh nhận request.
5. **Đánh đồng binding với validation**: dữ liệu đổi được kiểu chưa chắc hợp lệ nghiệp vụ. Giải pháp: bật validator, kiểm tra cả lỗi chuyển kiểu và lỗi ràng buộc.
6. **Bỏ qua kiểm soát thuộc tính được bind**: request có thể gửi thêm tên thuộc tính không mong muốn. Giải pháp: DTO đầu vào chuyên dụng, **setAllowedFields** nơi phù hợp và danh sách trường rõ ràng.

**Quy tắc thực hành:** xác định hợp đồng của từng trường, chuẩn hóa khi còn biết biểu diễn thô và trước lúc chuyển kiểu nếu ứng dụng kiểm soát được bước đó; dùng editor/converter/formatter đúng phạm vi Spring hỗ trợ; sau cùng để conversion và validation báo lỗi chính xác.