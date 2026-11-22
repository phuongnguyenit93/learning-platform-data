# JavaBean với getter, setter và constructor không tham số trong Spring Data Binding

Một **JavaBean** là cách thiết kế đối tượng Java có các thuộc tính (*properties*) được nhận diện theo quy ước phương thức truy cập, chẳng hạn `getEmail()` và `setEmail(...)`. Trong Spring MVC, một JavaBean có **constructor không tham số** và các **setter** tương ứng là lựa chọn quen thuộc cho đối tượng nhận dữ liệu form qua `@ModelAttribute`. Spring có thể tạo đối tượng, đọc tên tham số từ request, chuyển kiểu rồi gán các giá trị vào thuộc tính thông qua cơ chế *property binding*.

Bài này tập trung vào đối tượng đầu vào: JavaBean cần được thiết kế như thế nào, vì sao có getter/setter và constructor rỗng, Spring sử dụng chúng ra sao, và những lỗi gì xảy ra khi một phần của cấu trúc đó không phù hợp.

> Phạm vi: JavaBean là một quy ước của Java, không đồng nghĩa với *Spring-managed bean* được khai báo bởi `@Component` hoặc `@Bean`. Ngoài JavaBean mutable, Spring hiện đại còn hỗ trợ **constructor binding** cho các class/record bất biến; vì thế constructor không tham số **không phải yêu cầu bắt buộc của mọi `@ModelAttribute`**.

## 1. Ba thành phần nền tảng của JavaBean

Một JavaBean nhận dữ liệu thường có:

1. **Trường lưu trạng thái**, thường đặt `private` để các phần khác truy cập thông qua phương thức.
2. **Getter** để đọc giá trị và **setter** để ghi giá trị theo quy ước JavaBeans. Với field đọc/ghi, getter/setter là cầu nối giữa tên thuộc tính và code Java.
3. **Constructor không tham số**, thường là `public`, để công cụ/framework có thể khởi tạo một object trước khi điền dữ liệu qua setter.

Ví dụ:

```java
public class UserForm {
    private String username;
    private Integer age;

    public UserForm() {
        // Constructor không tham số
    }

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
```

Lời gọi `new UserForm()` tạo đối tượng với `username == null` và `age == null`. Sau `form.setUsername("An")` và `form.setAge(20)`, hai getter trả về `"An"` và `20`. Dù các field là `private`, Spring có thể ghi những **property** có setter phù hợp nhờ JavaBeans introspection và cơ chế property access.

**Không cần trường phải trùng tên với property bên trong.** Theo JavaBeans, tên property được suy ra từ phương thức: `getUsername()/setUsername(...)` biểu diễn property `username`. Code có thể lưu giá trị vào một backing field tên khác. Tuy vậy, dùng tên field trùng với property giúp dễ đọc và tránh nhầm lẫn.

## 2. Quy ước đặt tên getter và setter

| Property mong muốn | Getter | Setter | Ghi chú |
| --- | --- | --- | --- |
| `name` kiểu `String` | `getName()` | `setName(String value)` | Property có thể đọc và ghi |
| `age` kiểu `Integer` | `getAge()` | `setAge(Integer value)` | Kiểu getter và setter cần tương thích |
| `active` kiểu `boolean` | `isActive()` hoặc `getActive()` | `setActive(boolean value)` | `is...` là kiểu getter đặc biệt cho boolean |
| `enabled` kiểu `Boolean` | `getEnabled()` | `setEnabled(Boolean value)` | Với wrapper `Boolean`, nên dùng `get...` |
| `address` kiểu `Address` | `getAddress()` | `setAddress(Address value)` | Có thể chứa property lồng nhau |
| `URL` | `getURL()` | `setURL(String value)` | Tên acronym có quy tắc viết hoa riêng |

Quy tắc thường gặp:

- Getter không nhận tham số và trả kiểu giá trị. Setter nhận **một tham số** và thông thường trả `void`.
- Đối với property `firstName`, tên tiêu chuẩn là `getFirstName`/`setFirstName`, không phải `getFirstname`/`setFirstname`.
- Với `boolean` primitive, getter `isActive()` được JavaBeans nhận diện; setter vẫn là `setActive(boolean)`.
- Getter tồn tại nhưng không có setter thường biểu diễn property chỉ đọc. Setter không có getter có thể biểu diễn property chỉ ghi. Đối tượng form nhận giá trị qua **property binding** cần đường ghi hợp lệ cho các field dự định nhận.
- Không nên có các setter overload nhập nhằng cho cùng một property; phần mềm introspection có thể khó chọn kiểu đích nhất quán.
- Không thể dựa vào tên method tùy ý như `readAge()` hay `withAge(...)` rồi mặc định Spring sẽ xem đó là getter/setter JavaBeans.

**Quy tắc chữ hoa đặc biệt:** `java.beans.Introspector.decapitalize("Name")` trả `"name"`, còn `decapitalize("URL")` trả `"URL"` vì hai chữ cái đầu đều viết hoa. Đừng đoán property `uRL` nếu accessor là `getURL()`; tốt nhất chọn tên dễ hiểu và nhất quán trong DTO.

## 3. Constructor không tham số hoạt động ra sao?

Constructor không tham số là constructor gọi được mà không cung cấp đối số:

```java
public UserForm() {
}
```

Trong một JavaBean mutable điển hình, vòng đời là:

```text
Khởi tạo: new UserForm()
    ↓
Trạng thái mặc định của field
    ↓
setUsername("An")
    ↓
setAge(20)
    ↓
Object đã có dữ liệu đầu vào, sẵn sàng được validate/xử lý
```

### 3.1. Constructor mặc định do Java sinh

Nếu một class **không khai báo constructor nào**, trình biên dịch Java tạo một default constructor không tham số. Nhưng khi bạn tự khai báo bất kỳ constructor nào, Java **không tự sinh thêm** constructor rỗng.

```java
public class OrderForm {
    private String code;

    public OrderForm(String code) {
        this.code = code;
    }

    public String getCode() {
        return code;
    }

    public void setCode(String code) {
        this.code = code;
    }
}
```

Với class trên, `new OrderForm()` **không biên dịch** vì chỉ có `OrderForm(String)`. Nếu muốn hỗ trợ khởi tạo kiểu JavaBean truyền thống, khai báo thêm constructor không tham số:

```java
public OrderForm() {
}

public OrderForm(String code) {
    this.code = code;
}
```

Đây là **hai constructor trong cùng class**, không phải hai khai báo đứng độc lập ngoài class. Constructor không tham số chỉ cần có khi luồng tạo object sử dụng nó; một số cơ chế của Spring/Jackson có thể khởi tạo đối tượng bằng constructor có tham số, factory hoặc cơ chế khác.

### 3.2. Giá trị mặc định trước khi setter chạy

| Loại field | Giá trị Java ngay sau khởi tạo, nếu chưa gán giá trị khác |
| --- | --- |
| `String`, `Integer`, `Long`, object bất kỳ | `null` |
| `int`, `long` | `0` |
| `boolean` | `false` |
| `double` | `0.0` |
| `List<String>` | `null`, trừ khi khởi tạo sẵn, chẳng hạn `new ArrayList<>()` |

Constructor có thể thiết lập các giá trị ban đầu; initializer của field cũng có thể làm điều đó. Khi một request **không gửi tên field nào đó**, hãy kiểm tra giá trị mặc định và trạng thái object thực tế; không nên khẳng định mọi field bị thiếu sẽ có giá trị `null`.

Với field tùy chọn, `Integer` thường cho phép phân biệt “không có giá trị” (`null`) với `0`. Với checkbox dùng `boolean`, trạng thái thiếu input có thể để lại `false` trên object mới. Trong HTML, checkbox không được chọn thường không gửi cặp tên/giá trị; Spring có cơ chế field marker riêng khi dùng form binding.

## 4. Ví dụ Java 17+ chạy độc lập: tạo JavaBean và kiểm tra property

Ví dụ sau **không cần Spring**; bạn có thể dùng JDK 17+ để thấy JavaBean được tạo, được gán qua setter và được JavaBeans introspection nhận diện.

**Tệp `JavaBeanDemo.java`:**

```java
import java.beans.IntrospectionException;
import java.beans.Introspector;
import java.beans.PropertyDescriptor;
import java.util.Arrays;
import java.util.Comparator;

public class JavaBeanDemo {

    public static class RegistrationForm {
        private String email;
        private Integer age;
        private boolean subscribed;

        public RegistrationForm() {
        }

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }

        public Integer getAge() {
            return age;
        }

        public void setAge(Integer age) {
            this.age = age;
        }

        public boolean isSubscribed() {
            return subscribed;
        }

        public void setSubscribed(boolean subscribed) {
            this.subscribed = subscribed;
        }
    }

    public static void main(String[] args)
            throws IntrospectionException {
        RegistrationForm form = new RegistrationForm();
        form.setEmail("an@example.org");
        form.setAge(24);
        form.setSubscribed(true);

        System.out.println(
                form.getEmail() + " / " +
                form.getAge() + " / " +
                form.isSubscribed()
        );

        PropertyDescriptor[] properties = Introspector
                .getBeanInfo(RegistrationForm.class, Object.class)
                .getPropertyDescriptors();

        Arrays.stream(properties)
                .sorted(Comparator.comparing(PropertyDescriptor::getName))
                .forEach(property -> System.out.println(
                        property.getName() +
                        ":read=" + (property.getReadMethod() != null) +
                        ",write=" + (property.getWriteMethod() != null)
                ));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac JavaBeanDemo.java
java JavaBeanDemo
```

**Stdout mong đợi:**

```text
an@example.org / 24 / true
age:read=true,write=true
email:read=true,write=true
subscribed:read=true,write=true
```

Giải thích:

- `RegistrationForm` là nested class `static`, nên có thể được khởi tạo mà không cần một instance của `JavaBeanDemo`. Nếu là non-static inner class, constructor thực tế cần liên kết với outer instance, gây bất tiện cho các cơ chế khởi tạo thông thường.
- `Introspector.getBeanInfo(..., Object.class)` loại trừ các property chỉ có từ `Object` (chẳng hạn `class`), để bảng chỉ còn các property do `RegistrationForm` định nghĩa.
- `PropertyDescriptor` cho biết property có read method, write method hay cả hai; đó là cách kiểm tra quy ước, **chưa phải thao tác bind HTTP request**.
- Chữ `subscribed` được phát hiện từ `isSubscribed()` và `setSubscribed(boolean)`, dù accessor đọc không bắt đầu bằng `get`.

## 5. Spring MVC sử dụng JavaBean này trong `@ModelAttribute`

Khi controller khai báo `@ModelAttribute` cho dữ liệu form URL-encoded, Spring có thể lấy hoặc tạo object đích rồi bind request parameters vào các property được phép ghi. Ví dụ sau thuộc **ứng dụng Spring MVC chạy trên Servlet stack**, không phải chương trình Java SE độc lập.

**Tệp `RegistrationForm.java`** (trong package `demo.web`):

```java
package demo.web;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class RegistrationForm {
    @NotBlank
    @Email
    private String email;

    @NotNull
    @Min(18)
    private Integer age;

    private boolean subscribed;

    public RegistrationForm() {
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }

    public boolean isSubscribed() {
        return subscribed;
    }

    public void setSubscribed(boolean subscribed) {
        this.subscribed = subscribed;
    }
}
```

**Tệp `RegistrationController.java`** (cùng package):

```java
package demo.web;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.stream.Collectors;

@RestController
@RequestMapping("/registrations")
public class RegistrationController {

    @InitBinder("registrationForm")
    public void initRegistrationBinder(WebDataBinder binder) {
        binder.setAllowedFields("email", "age", "subscribed");
    }

    @PostMapping(
            path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    public ResponseEntity<String> register(
            @Valid @ModelAttribute("registrationForm")
            RegistrationForm form,
            BindingResult result) {

        if (result.hasErrors()) {
            String fields = result.getFieldErrors().stream()
                    .map(FieldError::getField)
                    .distinct()
                    .sorted()
                    .collect(Collectors.joining(","));
            return ResponseEntity.badRequest()
                    .body("invalid=" + fields);
        }

        String response = "email=" + form.getEmail()
                + ";age=" + form.getAge()
                + ";subscribed=" + form.isSubscribed();
        return ResponseEntity.ok(response);
    }
}
```

**Điều kiện chạy:** Hai class cần nằm trong source set của ứng dụng Spring MVC, được component scan phát hiện; với Spring Boot 3+ thường cần `spring-boot-starter-web` và `spring-boot-starter-validation` (hoặc cấu hình MVC và Jakarta Bean Validation tương đương). Controller chỉ là một phần của ứng dụng, nên không thể biên dịch/chạy nó bằng hai lệnh `javac`/`java` ở phần 4 nếu thiếu các thư viện và runtime Spring.

Gửi request:

```bash
curl -sS -i -X POST http://localhost:8080/registrations/form \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'email=an@example.org' \
  --data-urlencode 'age=24' \
  --data-urlencode 'subscribed=true'
```

Nếu server đã chạy và request hợp lệ, body của HTTP 200 là:

```text
email=an@example.org;age=24;subscribed=true
```

**Theo dõi luồng trong ví dụ:**

| Bước | Vai trò |
| --- | --- |
| Nhận `email=an@example.org&age=24&subscribed=true` | Servlet cung cấp request parameters |
| Tìm/tạo `registrationForm` | Spring có thể sử dụng constructor không tham số `RegistrationForm()` cho một object mới |
| Chọn property theo tên | `email`, `age`, `subscribed` đối chiếu với các setter JavaBeans |
| Chuyển kiểu | `"24"` thành `Integer 24` và `"true"` thành `boolean true` |
| Gán vào JavaBean | Spring sử dụng property binding để ghi giá trị tương ứng |
| Validate | `@Valid` áp dụng constraint Jakarta Validation khi đã cấu hình validator |
| Đọc từ controller | Getter cung cấp dữ liệu đã được bind cho xử lý nghiệp vụ |

Trong tình huống bình thường với JavaBean mutable và constructor không tham số này, setter binding là phần trọng tâm. Tuy nhiên, `@ModelAttribute` có thể dùng một đối tượng đã có sẵn trong model hoặc session, hoặc dùng constructor binding; **đừng suy luận mọi lần xử lý request đều gọi `new RegistrationForm()`**.

`@InitBinder("registrationForm")` cấu hình property binding để chỉ nhận `email`, `age` và `subscribed`. Đây là lớp hạn chế đầu vào hữu ích bên cạnh việc thiết kế DTO đúng phạm vi. Nó không thay thế validation và không nên hiểu là kiểm soát mọi cơ chế constructor binding.

## 6. Từ tên field HTML đến setter Java

Với form:

```html
<form method="post" action="/registrations/form">
  <input type="email" name="email" value="an@example.org">
  <input type="number" name="age" value="24">
  <input type="checkbox" name="subscribed" value="true" checked>
  <button type="submit">Đăng ký</button>
</form>
```

Browser gửi các tên được khai báo trong thuộc tính **`name`**; thuộc tính `id` chủ yếu phục vụ liên kết label/CSS/JS và không quyết định tên key trong payload. Khi binding:

```text
name="email"        -> property "email"       -> setEmail(String)
name="age"          -> property "age"         -> setAge(Integer)
name="subscribed"   -> property "subscribed"  -> setSubscribed(boolean)
```

Cách Spring đổi text thành `Integer`/`boolean` được quyết định bởi conversion service/formatter/editor đã đăng ký, không phải JavaBean getter/setter tự đổi kiểu. Nếu gửi `age=abc`, Spring không thể chuyển thành `Integer` và sinh lỗi binding. Nếu gửi `age=17`, việc chuyển sang số có thể thành công nhưng vi phạm `@Min(18)` ở bước validation. Với controller trên, nếu chỉ có một lỗi:

- Request có `age=abc` có thể trả body `invalid=age` cùng HTTP 400.
- Request có `age=17` cũng trả `invalid=age` cùng HTTP 400, nhưng nguyên nhân là constraint `@Min(18)`.
- Request thiếu `email` sẽ không đạt `@NotBlank`; mặc định `email` trong object mới là `null`.

Trong tất cả tình huống này, `BindingResult` đứng **ngay sau** tham số `@ModelAttribute` để controller có thể xem lỗi. Nếu không có `BindingResult` phù hợp, Spring có thể xử lý lỗi bằng exception theo cơ chế MVC.

Đừng đánh đồng **property access** và **field access**: ở cơ chế property binding theo JavaBeans, Java field có thể `private`, nhưng setter hợp lệ mới là điểm ghi giá trị. Spring có hỗ trợ chế độ direct-field access khi được cấu hình riêng, nhưng không nên giả định đó là chế độ mặc định của ví dụ.

## 7. JavaBean chứa đối tượng lồng nhau và collection

Một JavaBean đầu vào có thể biểu diễn dữ liệu nhiều tầng. Ví dụ hai class lồng sau nằm trong cùng file minh họa (không cần tạo Spring controller khác):

```java
public class ProfileForm {
    private String displayName;
    private Address address = new Address();

    public ProfileForm() {
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }

    public static class Address {
        private String city;

        public Address() {
        }

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }
    }
}
```

Nếu dùng `@ModelAttribute ProfileForm`, tên form `displayName=Minh&address.city=Hue` có thể bind vào:

```text
ProfileForm
 ├── displayName = "Minh"
 └── address
     └── city = "Hue"
```

Ở đây `address.city` là **property path**: getter `getAddress()` dẫn đến bean `Address`, sau đó `setCity("Hue")` gán giá trị. Gán sẵn `new Address()` giúp object lồng tồn tại. Spring có khả năng tự tạo nested object với một số cấu hình và giới hạn auto-grow; nhưng không nên mặc định mọi cấu trúc null, interface hay collection đều có thể tự tạo được.

Tên như `items[0].sku` hoặc `tags[1]` có thể đại diện phần tử collection. Với list/array/map, kiểu phần tử, getter/setter, object khởi tạo, cấu hình binder và giới hạn auto-grow đều ảnh hưởng đến kết quả. Vì vậy, chỉ tạo nested object/collection cần thiết, đặt giới hạn input và xem lỗi trên `BindingResult` khi binder không thể truy cập hoặc chuyển kiểu.

## 8. Các trường hợp JavaBean không còn là lựa chọn duy nhất

Trong Spring MVC hiện đại, có hai cách thường gặp để nhận input vào object:

| Tiêu chí | Mutable JavaBean + no-arg constructor | Constructor binding / immutable input |
| --- | --- | --- |
| Khởi tạo | Tạo object rỗng rồi điền giá trị | Truyền giá trị vào constructor |
| Ghi property | Setter có thể ghi sau khi tạo object | Dữ liệu được đưa vào tham số constructor |
| Field | Thường có thể thay đổi | Có thể dùng `final` |
| Java record | Không phải JavaBean setter truyền thống | Phù hợp với constructor binding |
| Ưu điểm | Quen thuộc với HTML forms và property binding | Tập field được nhận rõ qua constructor |
| Lưu ý | Cần hạn chế field client được phép sửa | Tên constructor argument và conversion cần xác định đúng |

Ví dụ record Java 17:

```java
public record RegistrationInput(String email, Integer age) {
}
```

Record **không có** setter và không có no-arg constructor mặc định. Tuy vậy, Spring MVC hiện đại có thể sử dụng constructor binding theo tên tham số để tạo record qua `@ModelAttribute`; `@RequestBody` JSON lại dùng cơ chế deserialization của `HttpMessageConverter` (thường là Jackson), với cấu hình và điều kiện riêng. Vì vậy câu “mọi form trong Spring đều phải có JavaBean với constructor rỗng” là **không chính xác**.

Nếu một controller dùng `@ModelAttribute` cùng JavaBean mutable, điều đó cũng không tự động biến class thành Spring container bean; đối tượng form là *model attribute* của request. Còn `@Component`/`@Bean` liên quan đến đăng ký object trong ApplicationContext với một vòng đời khác.

## 9. Lỗi phổ biến khi xây dựng JavaBean đầu vào

| Vấn đề | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| Chỉ khai báo constructor có tham số, nhưng code yêu cầu `new Form()` | Java không còn tự sinh default constructor | Thêm no-arg constructor hoặc dùng rõ ràng constructor binding |
| Field `name` có getter nhưng không có setter | Property chỉ đọc đối với setter binding | Thêm setter phù hợp nếu chủ đích là mutable input |
| `setAge(String)` nhưng getter trả `Integer` | Kiểu accessor không nhất quán | Dùng một kiểu property rõ ràng, để converter chịu trách nhiệm |
| Đặt tên `getFullname()` khi form gửi `fullName` | Tên property suy ra có thể khác | Dùng `getFullName()/setFullName(...)` |
| Getter `isActive()` dùng cho kiểu wrapper không phù hợp | Quy ước getter boolean không nhất quán giữa thư viện | Với `Boolean`, ưu tiên `getActive()` |
| Setter private/package-private | Không phải JavaBeans public write method thông thường | Định nghĩa public setter khi cần property binding |
| Class là non-static inner class | Cần một instance của outer class để khởi tạo | Dùng top-level class hoặc `static` nested class |
| Field object lồng null/không có đường ghi | Binder không truy cập được property path | Khởi tạo nested object hoặc thiết kế constructor binding phù hợp |
| Thiếu `name` trên HTML input | Key không xuất hiện trong form request | Đặt `name` theo property path đúng |
| Trộn `@RequestBody` với cách gửi form URL-encoded | Chọn sai nguồn và cơ chế đọc body | Dùng `@ModelAttribute` cho form hoặc `@RequestBody` cho JSON |
| Gửi text sai kiểu, như `age=abc` | Conversion thất bại | Đọc `BindingResult` và trả lỗi theo field |
| Bind trực tiếp JPA entity có field `role`/`approved` | Client có thể gửi field ngoài giao diện | Dùng DTO đầu vào, giới hạn allowed fields |

**Lỗi bảo mật cần tránh:** chỉ ẩn field trên UI không làm field đó an toàn. Client có thể tự thêm `isAdmin=true` vào HTTP request; nếu entity có setter tương ứng và được bind không giới hạn, thuộc tính nhạy cảm có thể bị thay đổi (*mass assignment*). Luôn tạo input DTO chỉ chứa dữ liệu được phép nhập; cân nhắc `setAllowedFields(...)` khi dùng property binding. Validation ràng buộc giá trị, còn phạm vi field được phép bind là một quyết định riêng.

**Lưu ý Lombok:** `@Getter`, `@Setter` hoặc `@NoArgsConstructor` có thể sinh mã Java tương ứng, nhưng kết quả phụ thuộc annotation và cấu hình. Khi học cơ chế binding, nên viết accessor và constructor tường minh để xác định chính xác những method tồn tại sau biên dịch.

## 10. Cách kiểm tra một JavaBean trước khi đưa vào controller

Có thể kiểm tra nhanh theo trình tự sau:

1. **Tạo object được không?** Nếu chọn cách khởi tạo bằng no-arg constructor, class có constructor phù hợp, nhìn thấy được và không phụ thuộc một outer instance không?
2. **Tên property có đúng không?** Dùng `getX`/`setX` hoặc `isX` cho boolean, đối chiếu với tên `name` trong form; cần thì dùng `Introspector` để xem property descriptor.
3. **Setter có phù hợp với kiểu không?** Kiểm tra getter và setter thống nhất kiểu, converter có thể chuyển đầu vào hay không.
4. **Giá trị thiếu và mặc định đã rõ chưa?** Chọn `Integer` hay `int`, `Boolean` hay `boolean` theo nhu cầu phân biệt thiếu dữ liệu; khởi tạo nested property nếu cần.
5. **Validation đã đặt đúng mục tiêu chưa?** `@NotBlank` cho chuỗi, `@NotNull` cho bắt buộc, `@Min` cho số, `@Valid` cho object lồng nếu cần cascade validation.
6. **Chỉ nhận field cho phép?** DTO nên chứa đúng các field client được phép đặt; giới hạn property binding nếu cần.
7. **Đã thử request thực tế?** Test một case hợp lệ, một case thiếu field, một case sai kiểu và một case vi phạm constraint. Xem `BindingResult` thay vì chỉ nhìn kết quả thành công.

### Bài tự luyện

Tạo `BookForm` có `title: String`, `pages: Integer` và `published: boolean`. Viết một constructor không tham số, getter/setter cho cả ba thuộc tính. Tạo object bằng `new BookForm()`, gán `title="Java Basics"`, `pages=180`, `published=true`; sau đó in kết quả từ getter.

Dự đoán điều gì xảy ra nếu:

- Đổi `setPages(Integer)` thành `setPageCount(Integer)` mà tên form vẫn là `pages`.
- Thêm constructor `BookForm(String title)` và bỏ constructor không tham số, nhưng code vẫn gọi `new BookForm()`.
- Form gửi `pages=xyz` để Spring bind vào `Integer pages`.
- Dùng record `BookInput(String title, Integer pages)` và kỳ vọng Spring gọi `setPages(...)`.

**Đáp án định hướng:** trường hợp đầu mất đường ghi theo property `pages`; trường hợp hai gây lỗi biên dịch ở lời gọi constructor rỗng; trường hợp ba là lỗi chuyển kiểu của binder; trường hợp bốn phải dùng constructor binding, vì record không có setter.

## Tài liệu đối chiếu

- [Oracle JavaBeans: Properties](https://docs.oracle.com/javase/tutorial/javabeans/writing/properties.html) — quy ước getter/setter, property boolean, read-only/write-only.
- [Spring Framework: Core Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html) — constructor binding, property binding và property paths.
- [Spring Framework: Spring MVC @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html) — cách tạo/tìm model object, binding và BindingResult.
- [Spring Framework: Web MVC Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html) — form binding, thiết kế input object và giới hạn field.
