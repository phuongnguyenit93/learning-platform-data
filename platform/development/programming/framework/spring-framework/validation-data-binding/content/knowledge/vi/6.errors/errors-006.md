# Giá trị bị từ chối, giá trị trường và kiểu trường trong Spring Errors

Khi Spring Framework liên kết dữ liệu đầu vào với một Java object, **giá trị người dùng vừa gửi có thể khác giá trị đang nằm trong object**. Điều này đặc biệt quan trọng khi chuyển kiểu thất bại: biểu mẫu gửi `age=abc`, thuộc tính Java `age` có kiểu `Integer` và trước đó chứa `21`. Spring không thể gán chuỗi `"abc"` vào thuộc tính này, nhưng vẫn cần ghi nhớ giá trị người dùng đã nhập để hiển thị lỗi.

Nhóm API `org.springframework.validation.Errors` giúp truy cập **giá trị của trường** và **kiểu trường**; `FieldError` lưu **giá trị bị từ chối** gắn với một lỗi cụ thể. Khi kết hợp chúng với `BindingResult`, ta có thể xử lý đúng thông báo, giữ dữ liệu biểu mẫu và tránh dùng nhầm một giá trị chưa hợp lệ trong nghiệp vụ.

Bài này tập trung vào các phương thức:

- `Errors.getFieldValue(String field)`: giá trị phù hợp cho ngữ cảnh báo lỗi/biểu mẫu của trường; có thể là giá trị bị từ chối thay vì giá trị đã gán trên object.
- `Errors.getFieldType(String field)`: kiểu Java của trường mà Spring xác định được; trả `Class<?>` hoặc `null`.
- `FieldError.getRejectedValue()`: giá trị bị từ chối của **một lỗi trường cụ thể**.
- `FieldError.isBindingFailure()`: lỗi liên quan đến binding (chẳng hạn sai kiểu) hay lỗi validation.
- `BindingResult.getRawFieldValue(String field)`: giá trị trường hiện tại ở dạng thô trên đối tượng đích, trong các triển khai binding phổ biến.

## 1. Ba thứ cần phân biệt

Giả sử đối tượng Java ban đầu:

~~~java
public class ProfileForm {
    private Integer age = 21;

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

Người dùng gửi giá trị văn bản `age=abc`. Một `DataBinder` dùng bean-property binding cố chuyển `"abc"` sang `Integer` nhưng thất bại. Thông tin sau lượt binding thông thường:

| Câu hỏi | API / vị trí | Kết quả trong ví dụ |
|---|---|---|
| Người dùng nhập gì nhưng không chuyển được? | `getFieldError("age").getRejectedValue()` | `"abc"` (`String`) |
| Giá trị nào nên đưa lại vào trường của form khi có lỗi? | `errors.getFieldValue("age")` | `"abc"` |
| Giá trị thật đang ở thuộc tính Java? | `form.getAge()` | `21` |
| Giá trị thô mà `BindingResult` đọc từ target? | `result.getRawFieldValue("age")` | `21` |
| Kiểu khai báo cho thuộc tính `age`? | `errors.getFieldType("age")` | `Integer.class` |
| Đây có phải lỗi binding? | `fieldError.isBindingFailure()` | `true` |
| Có lỗi cho trường này không? | `errors.hasFieldErrors("age")` | `true` |

**Điểm mấu chốt:** `"abc"` là chuỗi người dùng đã gửi nhưng không chuyển được thành `Integer`; nó không trở thành giá trị `age` của target. `getFieldType("age")` nói về **kiểu trường đích**, không phải kiểu runtime của giá trị bị từ chối. Đồng thời, `getRawFieldValue` không phải tên gọi khác của “HTTP raw input”.

## 2. Mỗi API trả về điều gì?

### 2.1. `Errors.getFieldValue(field)`

Khai báo API về mặt ý nghĩa:

~~~java
Object value = errors.getFieldValue("age");
~~~

Theo hợp đồng của `Errors`, phương thức trả về giá trị hiện tại liên quan đến trường: có thể là giá trị của bean property, hoặc giá trị được gửi nhưng bị từ chối trong một lượt binding. Điều đó giúp form hiển thị lại điều người dùng đã nhập ngay cả khi xảy ra `typeMismatch`.

Cần nhớ:

- Nếu **không có lỗi binding** của trường, giá trị thường bắt nguồn từ property đã bind. Với một số kiểu và `PropertyEditor`/`Formatter`, giá trị có thể đã được định dạng cho ngữ cảnh hiển thị.
- Nếu có `FieldError` do binding thất bại, Spring có thể ưu tiên rejected value để giữ đầu vào chưa chuyển kiểu được.
- Giá trị trả về có kiểu `Object`, không có bảo đảm luôn là `String`, `Integer` hoặc đối tượng nào cụ thể. Phải kiểm tra loại giá trị hoặc dùng formatter phù hợp trước khi xử lý.
- Trường không tồn tại, target chưa thể tạo, hoặc giá trị rỗng có thể dẫn đến kết quả `null` tùy triển khai/bối cảnh. Không được suy luận “không có lỗi” chỉ từ `getFieldValue(field) == null`.

`getFieldValue` là API **quan sát trạng thái phục vụ báo lỗi và nhập liệu**, không phải lời hứa rằng giá trị trả về đã qua toàn bộ validation.

### 2.2. `Errors.getFieldType(field)`

~~~java
Class<?> type = errors.getFieldType("age");
~~~

API cố xác định **kiểu Java của property**, chẳng hạn `Integer.class`, `String.class`, `LocalDate.class`, `BigDecimal.class` hoặc `int.class`, tùy khai báo. Trong cơ chế bean-property binding, Spring thường có thể đọc loại thuộc tính từ getter/setter và metadata dù giá trị hiện tại là `null`.

Ví dụ:

~~~java
Class<?> ageType = errors.getFieldType("age");
if (ageType != null) {
    System.out.println(ageType.getName()); // java.lang.Integer
}
~~~

Các lưu ý thiết yếu:

- `Integer.class` là kiểu kỳ vọng của trường `age`; nó không biến `"abc"` thành `Integer`.
- Với trường khai báo `int`, kết quả có thể là `int.class` và `getName()` là `"int"`, không phải `"java.lang.Integer"`.
- `null` ở `getFieldType` có nghĩa **Spring không xác định được kiểu**, không khẳng định trường có kiểu `null`.
- Các triển khai `Errors` khác nhau có mức hỗ trợ suy ra kiểu khác nhau; không tự giả định mọi `Errors` đều gắn với JavaBean có đầy đủ type descriptor.
- Không nên dựa vào một tên kiểu Java do client gửi lên để quyết định parse hay phân quyền. Tên kiểu lấy từ metadata server là thông tin hỗ trợ, không phải điều kiện xác thực giá trị đầu vào.

### 2.3. `FieldError.getRejectedValue()`

~~~java
FieldError ageError = errors.getFieldError("age");
if (ageError != null) {
    Object rejected = ageError.getRejectedValue();
}
~~~

`FieldError` đại diện **một lỗi của một trường**. Nó chứa tên trường (`getField()`), các mã lỗi (`getCode()` / `getCodes()`), thông điệp (`getDefaultMessage()`), giá trị bị từ chối và cờ lỗi binding.

Giá trị bị từ chối **không nhất thiết là chuỗi HTTP nguyên gốc**:

- Với lỗi chuyển kiểu `age=abc` sang `Integer`, rejected value thường là `"abc"` (chuỗi chưa chuyển được).
- Với lỗi validation “tuổi phải từ 18” sau khi `age=16` đã chuyển thành `Integer`, rejected value có thể là chính `Integer.valueOf(16)`.
- Khi trường bị thiếu hoặc giá trị rỗng được chuyển thành `null`, `getRejectedValue()` có thể là `null`. Điều đó **không tự phân biệt** missing, explicit null, hay lỗi do một quy tắc validation.
- Một trường có thể có nhiều `FieldError`; `getFieldError("age")` chỉ lấy lỗi đầu tiên. Muốn xử lý tất cả, dùng `getFieldErrors("age")`.

Cờ `isBindingFailure()` giúp phân biệt loại lỗi:

~~~java
if (ageError.isBindingFailure()) {
    // Ví dụ: lỗi chuyển đổi hoặc gán property.
} else {
    // Ví dụ: validator đã từ chối giá trị chuyển kiểu thành công.
}
~~~

Không suy ra mọi `FieldError` là lỗi chuyển kiểu, và cũng không suy ra `getRejectedValue()` chỉ có khi `isBindingFailure() == true`.

### 2.4. `BindingResult.getRawFieldValue(field)`

`BindingResult` mở rộng `Errors` và cung cấp dữ liệu binding chi tiết hơn:

~~~java
BindingResult result = binder.getBindingResult();
Object rawTargetValue = result.getRawFieldValue("age");
~~~

Phương thức này lấy **giá trị trường ở dạng thô theo binding result**, thông thường đọc trực tiếp property hiện có trên target, không qua định dạng để đưa lên form. Vì vậy, khi `age=abc` không gán được và target vẫn chứa 21, `getRawFieldValue("age")` cho kết quả 21 trong ví dụ JavaBean bên dưới.

Tên “raw” ở đây **không có nghĩa** “nguyên văn bytes HTTP request”. Nếu cần phân tích request gốc, phải dựa trên thông tin của web layer và các quy tắc xử lý dữ liệu tương ứng; tuyệt đối không dùng `getRawFieldValue` làm bằng chứng rằng đó là giá trị client vừa gửi.

## 3. Luồng khi bind lỗi và khi validate lỗi

~~~text
                  Dữ liệu đầu vào
                        |
                        v
                Spring DataBinder
                        |
               Thử chuyển đổi kiểu
                        |
          +-------------+--------------+
          |                            |
        Thành công                 Thất bại
          |                            |
    Gán vào target                Không gán được
          |                            |
    Có thể validate               Ghi FieldError
          |                            |
   Validator có thể               rejectedValue = input
   rejectValue(...)
          |                            |
   FieldError thường              bindingFailure = true
   bindingFailure = false
          |                            |
          +-------------+--------------+
                        |
                        v
             Errors / BindingResult
                        |
         +--------------+---------------+
         |              |               |
   getFieldValue  getFieldType   getFieldError
   hiển thị form  kiểu kỳ vọng   rejectedValue
~~~

Trong lượt property binding thông thường, một lỗi chuyển kiểu được Spring xử lý thành `FieldError` để ứng dụng báo lại. Một số trường khác vẫn có thể bind thành công. Tuy nhiên, **một target được bind một phần chưa phải dữ liệu hợp lệ để lưu**.

Validation diễn ra sau khi các giá trị có thể bind được đưa vào object, tùy cách controller hoặc binder được cấu hình. Một validation error có rejected value là **giá trị đã chuyển đổi thành công**. Cơ chế này khác với việc bắt một giá trị sai kiểu trước khi gán.

## 4. Ví dụ chạy được với Java 17 và Spring Framework

Ví dụ sau tạo hai lượt binding riêng biệt để so sánh:

1. `age="abc"`: không chuyển được thành `Integer`, sinh lỗi binding.
2. `age="16"`: chuyển thành `Integer.valueOf(16)` thành công nhưng bị quy tắc tuổi tối thiểu từ chối bằng `rejectValue`.

Dự án nhỏ dùng Maven để lấy dependency Spring nhất quán. Thư mục:

~~~text
field-errors-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── FieldValuesDemo.java
~~~

**Tệp `pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>field-errors-demo</artifactId>
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
                <version>3.6.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` cung cấp các API validation/binding trong ví dụ, cùng các dependency bắc cầu cần thiết. Không cần Spring Boot, server HTTP hay database để chạy chương trình này.

**Tệp `src/main/java/demo/FieldValuesDemo.java`:**

~~~java
package demo;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;

public final class FieldValuesDemo {

    public static final class ProfileForm {
        private String name;
        private Integer age = 21;
        private String city;
        private String nickname;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public Integer getAge() {
            return age;
        }

        public void setAge(Integer age) {
            this.age = age;
        }

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }

        public String getNickname() {
            return nickname;
        }

        public void setNickname(String nickname) {
            this.nickname = nickname;
        }
    }

    public static void main(String[] args) {
        conversionFailure();
        validationFailure();
    }

    private static void conversionFailure() {
        ProfileForm target = new ProfileForm();
        DataBinder binder = new DataBinder(target, "profile");
        binder.setAllowedFields("name", "age", "city", "nickname");

        MutablePropertyValues input = new MutablePropertyValues();
        input.add("name", "Lan");
        input.add("age", "abc");
        input.add("city", "Huế");
        binder.bind(input);

        BindingResult result = binder.getBindingResult();
        Errors errors = result;

        FieldError error = result.getFieldError("age");
        if (error == null) {
            throw new AssertionError("Expected a type mismatch for age");
        }

        System.out.println("target.name=" + target.getName());
        System.out.println("target.age=" + target.getAge());
        System.out.println("target.city=" + target.getCity());
        System.out.println("age.hasError=" + errors.hasFieldErrors("age"));
        System.out.println("age.code=" + error.getCode());
        System.out.println("age.rejected=" + error.getRejectedValue());
        System.out.println("age.bindingFailure=" + error.isBindingFailure());
        System.out.println("age.fieldValue=" + errors.getFieldValue("age"));
        System.out.println("age.fieldType="
                + errors.getFieldType("age").getName());
        System.out.println("age.rawTargetValue="
                + result.getRawFieldValue("age"));
        System.out.println("city.fieldValue=" + errors.getFieldValue("city"));
        System.out.println("nickname.fieldValue="
                + errors.getFieldValue("nickname"));
        System.out.println("nickname.fieldType="
                + errors.getFieldType("nickname").getName());
    }

    private static void validationFailure() {
        ProfileForm target = new ProfileForm();
        DataBinder binder = new DataBinder(target, "profile");

        MutablePropertyValues input = new MutablePropertyValues();
        input.add("age", "16");
        binder.bind(input);

        BindingResult result = binder.getBindingResult();
        if (target.getAge() != null && target.getAge() < 18) {
            // Giả lập một quy tắc validation của ứng dụng.
            result.rejectValue("age", "age.minimum",
                    "Tuổi phải từ 18");
        }

        FieldError error = result.getFieldError("age");
        if (error == null) {
            throw new AssertionError("Expected validation error for age");
        }

        System.out.println("validated.targetAge=" + target.getAge());
        System.out.println("validated.rejected=" + error.getRejectedValue());
        System.out.println("validated.rejectedType="
                + error.getRejectedValue().getClass().getName());
        System.out.println("validated.bindingFailure="
                + error.isBindingFailure());
        System.out.println("validated.fieldType="
                + result.getFieldType("age").getName());
    }
}
~~~

**Chạy bằng JDK 17+ và Maven 3.9+:**

~~~bash
cd field-errors-demo
mvn -q compile exec:java -Dexec.mainClass=demo.FieldValuesDemo
~~~

Phần **stdout của chương trình** với Spring Framework 6.2.12 và cấu hình binder mặc định:

~~~text
target.name=Lan
target.age=21
target.city=Huế
age.hasError=true
age.code=typeMismatch
age.rejected=abc
age.bindingFailure=true
age.fieldValue=abc
age.fieldType=java.lang.Integer
age.rawTargetValue=21
city.fieldValue=Huế
nickname.fieldValue=null
nickname.fieldType=java.lang.String
validated.targetAge=16
validated.rejected=16
validated.rejectedType=java.lang.Integer
validated.bindingFailure=false
validated.fieldType=java.lang.Integer
~~~

Maven `-q` giảm log build; bảng trên mô tả **các dòng do mã Java in ra**, không hứa hẹn mọi môi trường đều không có thông báo bổ sung từ Maven/JVM.

**Giải thích phần binding lỗi:** `age="abc"` tạo `FieldError` mã `typeMismatch`. Vì setter không nhận được giá trị hợp lệ nên `target.age` vẫn bằng 21. `Errors.getFieldValue("age")` giúp giữ `"abc"` để hiển thị lại trong biểu mẫu, còn `BindingResult.getRawFieldValue("age")` cho thấy giá trị target thực là 21. `getFieldType("age")` vẫn là `Integer.class`. Các trường `name` và `city` bind thành công.

**Giải thích phần validation lỗi:** chuỗi `"16"` được chuyển thành `Integer(16)` và gán thành công. Quy tắc tuổi tối thiểu sau đó gọi `rejectValue`; `FieldError` có rejected value là `Integer(16)` và `isBindingFailure() == false`. Vì vậy không thể kết luận “rejected value luôn là chuỗi không chuyển kiểu được”.

**Lưu ý:** mã `age.minimum` ở ví dụ là mã lỗi ứng dụng tự đặt; `typeMismatch` thuộc cơ chế báo lỗi chuyển đổi thông thường của Spring. Không mặc định mọi mã lỗi hoặc nội dung thông báo đều cố định khi thay đổi converter, validator và cấu hình message code.

## 5. Khi trường không có lỗi, có lỗi, hoặc không có giá trị

Tùy cơ chế binding và formatter, `getFieldValue(field)` và `getRejectedValue()` có thể khác nhau hoặc cùng biểu diễn một giá trị. Xem các tình huống:

| Đầu vào và điều kiện | Target sau binding | `getFieldValue` | `getRejectedValue` |
|---|---|---|---|
| `name=Lan`, hợp lệ | `"Lan"` | Thường `"Lan"` | Không có `FieldError` để gọi |
| `age=abc`, property `Integer age=21` | Vẫn `21` | Thường `"abc"` | `"abc"` trên lỗi binding |
| `age=16` rồi validator từ chối tuổi dưới 18 | `16` | Thường giá trị `16` (có thể qua format) | `Integer(16)` trên lỗi validation |
| `nickname` không gửi, property là `String nickname=null` | `null` | Thường `null` | Không có lỗi nếu không bị ràng buộc bắt buộc |
| Giá trị sai nhưng target ban đầu cũng là `null` | Có thể giữ `null` | Có thể là input bị từ chối | Phụ thuộc giá trị được ghi vào lỗi |

Với nhiều formatter hoặc editor, `getFieldValue` phục vụ một dạng biểu diễn khác dữ liệu trong property. Ví dụ giá trị tiền hoặc ngày có thể được định dạng theo locale; **không dựa vào `String.valueOf(getFieldValue(...))` để tái tạo giá trị chuẩn nhằm lưu database**.

Một điểm thường gây nhầm lẫn: **không có `FieldError`** và **`FieldError.getRejectedValue() == null`** không giống nhau. Trước khi đọc rejected value, phải kiểm tra đối tượng `FieldError` có tồn tại.

## 6. Spring MVC: đọc các giá trị từ BindingResult

Trong controller dùng form hoặc query parameters với `@ModelAttribute`, Spring MVC bind vào đối tượng và tập hợp lỗi trong `BindingResult`. Sau đây là **mã tích hợp trong một dự án Spring MVC**, không phải lớp chạy độc lập; giả sử bean `ProfileForm` có các thuộc tính được khai báo và một view có tên `profile/form`.

~~~java
import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

@Controller
class ProfileController {

    @PostMapping("/profiles")
    String submit(
            @Valid @ModelAttribute("profile") ProfileForm form,
            BindingResult result) {

        if (result.hasErrors()) {
            Errors errors = result;
            FieldError ageError = errors.getFieldError("age");

            if (ageError != null) {
                Object entered = errors.getFieldValue("age");
                Object rejected = ageError.getRejectedValue();
                Class<?> expectedType = errors.getFieldType("age");

                // Chuyển các lỗi thành thông báo an toàn cho view.
                // Không in nguyên rejected value vào log/HTML.
            }

            return "profile/form";
        }

        // Chỉ xử lý nghiệp vụ khi không còn binding/validation error.
        return "profile/success";
    }
}
~~~

Đặt `BindingResult` **ngay sau** đối tượng `@ModelAttribute` mà nó mô tả. Với `@Valid`, Bean Validation có thể bổ sung lỗi vào cùng kết quả. Đối tượng form có thể chứa vài trường đã bind thành công, do đó phải kiểm tra `result.hasErrors()` trước khi lưu hoặc gọi nghiệp vụ có tác động.

**Phân biệt cơ chế:** Với JSON `@RequestBody`, Spring sử dụng `HttpMessageConverter` (thường dựa trên Jackson) để đọc dữ liệu. JSON sai cú pháp hoặc không deserialize được có thể gây ngoại lệ trước khi có một `BindingResult` như trên. Không giả định mỗi lỗi chuyển kiểu JSON đều là `FieldError` của `@ModelAttribute`; xử lý các ngoại lệ HTTP message conversion bằng cơ chế phù hợp, chẳng hạn `@RestControllerAdvice`.

### Hiển thị dữ liệu biểu mẫu an toàn

Mục tiêu thường là giữ giá trị người dùng đã nhập sau một lỗi:

~~~text
Tuổi: abc
Lỗi: Tuổi phải là số nguyên hợp lệ.
Tên: Lan
Thành phố: Huế
~~~

Không nên lấy `form.getAge()` (vẫn có thể là 21) để thay thế một cách mù quáng cho dữ liệu đã nhập sai khi render form. Các thư viện view tích hợp Spring có thể sử dụng `BindingResult` để chọn giá trị thích hợp. Nếu tự xây HTML/JSON, phải ánh xạ có kiểm soát, escape nội dung theo output context và chỉ trả thông tin mà người gọi được phép xem.

## 7. Cách duyệt lỗi và tránh nhầm nhiều lỗi trên một trường

Sử dụng `getFieldError("age")` khi chỉ cần lỗi đầu tiên; sử dụng `getFieldErrors("age")` nếu muốn xử lý mọi lỗi của `age`:

~~~java
for (FieldError error : result.getFieldErrors("age")) {
    String field = error.getField();
    String code = error.getCode();
    boolean bindingFailure = error.isBindingFailure();

    // Các giá trị này giúp chọn thông báo mà ứng dụng đã định nghĩa.
    // error.getRejectedValue() có thể là null hoặc dữ liệu nhạy cảm.
}
~~~

Mã lỗi có thể dùng với `MessageSource` để tạo câu chữ phù hợp ngôn ngữ:

- `typeMismatch`: “Giá trị không đúng định dạng yêu cầu.”
- `age.minimum`: “Tuổi phải từ 18.”
- `NotNull`: “Vui lòng nhập giá trị.”
- Các mã cụ thể hơn như `typeMismatch.profile.age` có thể xuất hiện trong danh sách mã do `MessageCodesResolver` tạo, tùy cấu hình.

**Thông báo ở trên là ví dụ do ứng dụng định nghĩa**, không phải các bản dịch cố định mà Spring tự sinh cho mọi cấu hình. `FieldError.getCode()` thường là mã tổng quát; `getCodes()` cho danh sách mã để chọn message. Không parse chuỗi exception message để quyết định nghiệp vụ.

Nếu một field có nhiều lỗi, đừng giả định lỗi đầu tiên là lỗi quan trọng nhất trong mọi trường hợp. Chọn quy tắc ưu tiên thông báo rõ ràng (ví dụ sai kiểu thì không yêu cầu người dùng đáp ứng thêm ràng buộc số học trên chính giá trị chưa chuyển được). Luồng validation cũng cần tránh thêm thông báo gây nhiễu cho trường đang bị binding failure.

## 8. Trường lồng nhau, loại nguyên thủy và giá trị null

### 8.1. Đường dẫn trường lồng nhau

Spring sử dụng tên trường dạng `address.zipCode` hoặc `items[0].price` tùy cấu trúc và cấu hình binding:

~~~java
FieldError nestedError = result.getFieldError("address.zipCode");
if (nestedError != null) {
    Object rejected = nestedError.getRejectedValue();
    Class<?> expected = result.getFieldType("address.zipCode");
}
~~~

Việc xác định kiểu phụ thuộc vào việc Spring có truy cập được metadata/property path hay không. Đối với path không hợp lệ, thuộc tính không tồn tại hoặc cấu trúc lồng nhau không thể đọc, kết quả có thể là `null` hoặc gây lỗi tùy bối cảnh; không hứa hẹn `getFieldType` sẽ xác định được mọi đường dẫn tùy ý.

### 8.2. `int` so với `Integer`

~~~java
private int primitiveAge;
private Integer boxedAge;
~~~

`primitiveAge` có giá trị mặc định 0; `boxedAge` có thể là `null`. `getFieldType("primitiveAge")` có thể trả `int.class`, còn `getFieldType("boxedAge")` trả `Integer.class`. Cả hai có thể từ chối `"abc"`, nhưng trạng thái target khi không gán được khác nhau.

Không dùng số 0 mặc định để kết luận chắc chắn client đã nhập 0. Nếu cần phân biệt dữ liệu thiếu với số 0 khi validation, thường dùng `Integer` cùng `@NotNull` ở request DTO.

### 8.3. Trường có giá trị null vẫn có thể có kiểu

Nếu `nickname == null` nhưng property được khai báo `String nickname`, triển khai bean-property binding vẫn có thể trả `String.class` qua metadata. Vì thế:

~~~java
Object value = result.getFieldValue("nickname");       // có thể null
Class<?> type = result.getFieldType("nickname");       // có thể String.class
~~~

`value == null` không kéo theo `type == null`. Khi xây thông báo, cũng nên phân biệt giá trị bị từ chối `null` với việc không có lỗi trường.

## 9. Lỗi thường gặp

**Lỗi 1 — dùng giá trị bị từ chối làm dữ liệu đã xác thực.** `getRejectedValue()` được lưu để giải thích lỗi, không phải để bỏ qua chuyển kiểu. Chỉ dùng dữ liệu sau khi binding, validation và các kiểm tra nghiệp vụ đều đạt yêu cầu.

**Lỗi 2 — cho rằng `getFieldValue` luôn đọc trực tiếp getter của entity.** Khi có binding failure, API có thể trả rejected input để hiển thị form. Cần đọc target qua getter hoặc `getRawFieldValue` nếu thật sự quan tâm trạng thái bean hiện tại.

**Lỗi 3 — cho rằng `getRawFieldValue` là giá trị request nguyên gốc.** Đây là API đọc giá trị thô của field theo binding result; trong tình huống sai kiểu có thể chính là giá trị cũ của target.

**Lỗi 4 — ép kiểu `getFieldValue("age")` sang `Integer`.** Khi `age=abc`, phương thức có thể trả `String`. Đoạn `(Integer) result.getFieldValue("age")` lúc đó sẽ ném `ClassCastException`. Dựa vào `getFieldType` để nhận biết kiểu đích, không phải để chứng minh đối tượng trả về đã là kiểu đó.

**Lỗi 5 — đọc `getRejectedValue()` khi chưa kiểm tra `FieldError` có tồn tại.** Với trường hợp lệ, `getFieldError(field)` có thể là `null`; luôn kiểm tra trước.

**Lỗi 6 — nhầm validation error với conversion error.** Khi một giá trị đã chuyển sang kiểu đích nhưng không qua quy tắc `@Min`, `@NotBlank` hoặc custom validator, rejected value vẫn có thể chứa giá trị Java hợp lệ về mặt kiểu. Dùng `isBindingFailure()` và mã lỗi để phân loại.

**Lỗi 7 — ghi toàn bộ rejected value ra log hoặc response.** Một trường nhạy cảm có thể chứa mật khẩu, token, số định danh hoặc thông tin cá nhân; array/object cũng có thể in ra gây nhiễu. Chỉ sử dụng tên trường trong allowlist và thông báo lỗi đã kiểm soát; hạn chế log, áp dụng masking/redaction và escape khi hiển thị.

**Lỗi 8 — dùng trực tiếp `@ModelAttribute` với entity và cho phép bind mọi property.** Việc này làm tăng nguy cơ gán cả những thuộc tính không được phép sửa. Nên bind vào form/DTO chuyên dụng, định nghĩa field được phép và kiểm tra quyền ở service. Trong trường hợp cần, cấu hình `DataBinder.setAllowedFields(...)` cho property binding.

**Lỗi 9 — đồng nhất field suppression với `FieldError`.** Một field bị chặn bởi `allowedFields` có thể xuất hiện trong `BindingResult.getSuppressedFields()` mà không tạo lỗi chuyển kiểu. Vì thế không chỉ kiểm tra `getFieldErrors()` khi có yêu cầu phát hiện input nhằm chỉnh sửa field không được phép.

## 10. Tình huống nên kiểm thử

Có thể viết unit test cho `DataBinder` và integration test với Spring MVC:

| Trường hợp | Kỳ vọng chính |
|---|---|
| `age="abc"`, target ban đầu 21 | Có `typeMismatch`; rejected `"abc"`; target vẫn 21; field type `Integer.class` |
| `age="16"` và validator yêu cầu ≥ 18 | Target thành `Integer(16)`; error `bindingFailure=false` |
| `age="21"` và mọi constraint hợp lệ | Không có `FieldError` cho `age` |
| `nickname=null`, property kiểu `String` | Field value có thể null; field type vẫn có thể là `String.class` |
| Hai field khác nhau cùng sai | Lấy được lỗi từng field; không dùng lỗi của field này cho field kia |
| Field bị chặn binding | Không bị gán; kiểm tra `getSuppressedFields()` riêng |
| Input chứa giá trị nhạy cảm | Response/log không vô tình lộ rejected value |
| Controller nhận form sai kiểu | Có `BindingResult` để hiển thị lại input; không chạy nhánh lưu dữ liệu |

Trong test không cần so khớp toàn bộ nội dung exception message vì thông báo phụ thuộc locale, converter, Spring version và cách ứng dụng giải quyết message codes. Nên kiểm tra field, loại lỗi, rejected value và trạng thái target.

## 11. Cách chọn đúng phương thức trong thực tế

Khi cần **hiển thị lại ô nhập mà người dùng vừa gửi**, ưu tiên cơ chế form binding của Spring hoặc `getFieldValue(field)` kèm escape/formatting an toàn.

Khi cần **giải thích một lỗi field cụ thể**, lấy `FieldError`, xem `getField()`, `getCode()` / `getCodes()`, `isBindingFailure()` và chỉ đọc `getRejectedValue()` nếu thực sự cần. Đừng nhúng rejected value tùy tiện vào thông báo.

Khi cần **biết Java type mà target đang mong đợi**, gọi `getFieldType(field)`, xử lý kết quả `null` và nhớ kiểu này không nhất thiết trùng kiểu runtime của input bị từ chối.

Khi cần **kiểm tra giá trị thực sự đang được giữ trong target**, dùng getter của form/DTO hoặc `BindingResult.getRawFieldValue(field)` theo ngữ nghĩa của triển khai. Và khi đã có lỗi binding/validation, không dùng giá trị trên target để thực hiện nghiệp vụ cho đến khi toàn bộ request đạt yêu cầu.

### Tài liệu tham khảo chính thức

- [Spring Framework Javadoc — Errors](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/Errors.html)
- [Spring Framework Javadoc — BindingResult](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework Javadoc — FieldError](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring Framework Javadoc — AbstractBindingResult](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/AbstractBindingResult.html)
- [Spring Framework — Validation, Data Binding and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
