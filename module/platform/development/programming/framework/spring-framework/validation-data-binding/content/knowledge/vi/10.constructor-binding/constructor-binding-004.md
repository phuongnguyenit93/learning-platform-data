# construct và đọc đối tượng được tạo bằng constructor binding

## 1. Mục tiêu và ngữ cảnh

Trong Spring Framework, **constructor binding** tạo một object mới bằng cách lấy dữ liệu đầu vào, ánh xạ chúng vào **tham số constructor**, chuyển kiểu và gọi constructor đó. Chủ đề này tập trung vào hai thao tác của `org.springframework.validation.DataBinder`:

1. **`construct(DataBinder.ValueResolver)`** để dựng đối tượng từ dữ liệu đầu vào khi ban đầu chưa có target.
2. **`getTarget()`** để đọc object Spring tạo được, kết hợp với **`getBindingResult()`** để kiểm tra lỗi trước khi sử dụng.

Ví dụ phù hợp: nhận `name=Lan`, `age=26`, `address.city=Hue` rồi dựng record `Signup` có thành phần `String`, `Integer` và một record `Address` lồng nhau. Constructor binding hữu ích với **record, DTO bất biến, class chỉ có constructor tham số**, đặc biệt khi không muốn phụ thuộc vào setter.

Nội dung sau áp dụng cho **Java 17+ và Spring Framework 6.2.x**. API `DataBinder.construct(...)` xuất hiện từ Spring 6.1; `ValueResolver.getNames()` xuất hiện từ 6.1.2. Các dự án Spring Boot 3.x cần kiểm tra phiên bản Spring Framework thực tế do dependency management cung cấp.

Sau bài học, bạn có thể:

- Chuẩn bị `DataBinder` đúng cách với target `null` và `ResolvableType`.
- Cài đặt `DataBinder.ValueResolver` để đưa dữ liệu vào constructor.
- Đọc object thành công bằng `getTarget()` và ép kiểu an toàn.
- Kiểm tra `BindingResult` trước khi dùng object.
- Phân biệt việc tạo object bằng constructor với việc ghi property và chạy validation.
- Xử lý nested object, lỗi conversion, tên tham số và dữ liệu không tin cậy.

## 2. Khi nào gọi `construct`?

Một `DataBinder` thường được tạo cho **object đã tồn tại**:

~~~java
Person person = new Person();
DataBinder binder = new DataBinder(person);
binder.bind(propertyValues);
~~~

Đây là **đoạn minh họa** cho property binding: `person` đã tồn tại, còn `bind(...)` tìm các property phù hợp để gán dữ liệu. `Person` và `propertyValues` phải được định nghĩa trong chương trình thực tế.

Constructor binding đi theo hướng khác:

~~~java
DataBinder binder = new DataBinder(null, "signup");
binder.setTargetType(ResolvableType.forClass(Signup.class));
binder.construct(valueResolver);

BindingResult result = binder.getBindingResult();
Object created = binder.getTarget();
~~~

Đoạn thứ hai cũng là **fragment**, sẽ được triển khai thành chương trình chạy được ở mục 4. Ý nghĩa từng bước:

1. `new DataBinder(null, "signup")`: chưa có đối tượng để bind; `"signup"` là tên logic dùng cho lỗi và model.
2. `setTargetType(ResolvableType.forClass(Signup.class))`: cho binder biết **kiểu cần tạo**. `ResolvableType` còn hỗ trợ mô tả kiểu generic khi cần.
3. `construct(valueResolver)`: hỏi resolver giá trị của các constructor argument, chuyển kiểu và dựng object.
4. `getBindingResult()`: kiểm tra lỗi tạo/binding.
5. `getTarget()`: lấy object được tạo; return type là `Object` nên cần kiểm tra/ép kiểu phù hợp.

**Không gọi `construct` như một cách khởi tạo lại target đã tồn tại.** API này mong đợi target ban đầu là `null` và đã được cấu hình target type. Nếu `getTarget()` đang có object, lời gọi không đúng tiền điều kiện. Cũng đừng gọi `construct` lặp lại chỉ để “đọc” object; sau lần tạo thành công, đọc bằng `getTarget()`.

## 3. Luồng xử lý nội bộ ở mức khái niệm

~~~text
Map / request parameters / nguồn dữ liệu
       name="Lan"
       age="26"
       address.city="Hue"
                   |
                   v
new DataBinder(null, "signup")
setTargetType(Signup.class)
                   |
                   v
          construct(ValueResolver)
                   |
          +--------+---------+
          |                  |
      Tìm tham số         ValueResolver
      constructor         tìm tên và giá trị
          |                  |
          +--------+---------+
                   |
           Convert theo kiểu
             String -> Integer
                   |
        Tạo Address (nested object)
                   |
         Gọi canonical constructor
                   |
        +----------+----------+
        |                     |
   Không có lỗi           Lỗi conversion
        |                     |
   getTarget()          getBindingResult()
        |               có FieldError
   Dùng Signup           Kiểm tra lỗi
~~~

Luồng trên giải thích trách nhiệm API; **không giả định** rằng mọi lỗi đều được chuyển thành một đối tượng `Signup` hoàn chỉnh. Nếu conversion thất bại, hãy kiểm tra `BindingResult` và trạng thái target. Nếu chính constructor ném ngoại lệ không liên quan đến conversion, lời gọi `construct` còn có thể phát sinh `BeanInstantiationException`; đó là đường lỗi cần phân biệt.

Spring có thể chọn data constructor phù hợp với kiểu đích. Thiết kế nên có **một constructor dữ liệu rõ ràng**. Record Java giúp xác định canonical constructor và tên các component. Khi có nhiều constructor, hành vi lựa chọn có thể dựa trên constructor mặc định và metadata; đừng tạo nhiều constructor tùy ý rồi trông chờ Spring tự suy ra “đúng cái cần dùng”.

## 4. Ví dụ Java hoàn chỉnh: construct và đọc target

Để thực hành không cần web server, dùng Spring `spring-context` vì `DataBinder` nằm trong module này. Spring sẽ kéo những module phụ thuộc cần thiết.

### 4.1. Cấu trúc project

~~~text
constructor-binding-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/ConstructDemo.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'constructor-binding-demo'
~~~

Tệp `build.gradle` cho Gradle Groovy DSL:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.ConstructDemo'
}
~~~

`6.2.18` là phiên bản cố định dùng cho ví dụ. Trong dự án Spring Boot thực tế, ưu tiên dependency management/BOM của Boot để chọn các phiên bản Spring tương thích.

### 4.2. Tệp `src/main/java/demo/ConstructDemo.java`

~~~java
package demo;

import java.util.Map;
import java.util.Set;

import org.springframework.core.ResolvableType;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public class ConstructDemo {

    public record Address(String city) {}

    public record Signup(String name, Integer age, Address address) {}

    private static DataBinder.ValueResolver fromMap(
            Map<String, ?> inputs) {

        return new DataBinder.ValueResolver() {
            @Override
            public Object resolveValue(String name, Class<?> type) {
                return inputs.get(name);
            }

            @Override
            public Set<String> getNames() {
                return inputs.keySet();
            }
        };
    }

    public static void main(String[] args) {
        Map<String, String> inputs = Map.of(
                "name", "Lan",
                "age", "26",
                "address.city", "Hue"
        );

        DataBinder binder = new DataBinder(null, "signup");
        binder.setTargetType(
                ResolvableType.forClass(Signup.class));

        binder.construct(fromMap(inputs));

        BindingResult errors = binder.getBindingResult();
        if (errors.hasErrors()) {
            errors.getAllErrors().forEach(error ->
                    System.out.println(error.getCode()));
            return;
        }

        Object target = binder.getTarget();

        if (!(target instanceof Signup created)) {
            throw new IllegalStateException(
                    "Không tạo được Signup");
        }

        System.out.println("name=" + created.name());
        System.out.println("age=" + created.age());
        System.out.println("city=" + created.address().city());
        System.out.println("objectName=" + binder.getObjectName());
        System.out.println("sameTarget=" +
                (errors.getTarget() == created));
    }
}
~~~

Đây là **một tệp Java độc lập trong project trên**, với package, imports và method `main` đầy đủ. Spring không cần controller để dùng `DataBinder` theo cách lập trình thủ công này.

### 4.3. Chạy chương trình và kết quả

Trong thư mục chứa `build.gradle`, với Gradle Wrapper đã được tạo:

~~~bash
./gradlew run
~~~

Trên Windows:

~~~powershell
.\gradlew.bat run
~~~

Ngoài thông tin tác vụ do Gradle in ra, stdout của chương trình Java khi dữ liệu hợp lệ là:

~~~text
name=Lan
age=26
city=Hue
objectName=signup
sameTarget=true
~~~

Giải thích từng dòng:

- `name=Lan`: giá trị `"Lan"` đi vào tham số `String name`.
- `age=26`: `"26"` được chuyển sang `Integer` trước khi gọi constructor.
- `city=Hue`: Spring dựng record con `Address("Hue")` từ path `address.city`.
- `objectName=signup`: tên do `new DataBinder(null, "signup")` cấu hình, không nhất thiết trùng tên Java class.
- `sameTarget=true`: khi tạo thành công, `BindingResult#getTarget()` trỏ tới cùng object với target đã lấy từ binder.

Bài dùng `Map.of` để mô phỏng dữ liệu input. Trong Spring MVC, nguồn thực tế có thể là form/query parameters do hạ tầng HTTP cung cấp. Cơ chế hỏi tên và giá trị vẫn dựa trên nguyên tắc tương tự.

## 5. Vai trò của `ValueResolver`: chính xác hai phương thức

Trong Spring 6.2.x, `DataBinder.ValueResolver` định nghĩa hai phương thức chính:

~~~java
Object resolveValue(String name, Class<?> type);

Set<String> getNames();
~~~

Đây là chữ ký API rút gọn để học, không phải source code định nghĩa lại interface.

**`resolveValue(name, type)`** được Spring gọi khi cần giá trị của một tham số constructor. `name` là tên được Spring xác định, có thể là path lồng nhau như `address.city`. `type` cho biết kiểu của tham số đích; resolver có thể trả giá trị thô và để binder thực hiện conversion.

Trong ví dụ, resolver dùng `inputs.get(name)`. Nó trả `"26"` cho tên `age`; binder chuyển chuỗi đó sang `Integer`. Nếu nguồn dữ liệu đã trả đúng kiểu `Integer`, cơ chế vẫn phù hợp. Nếu tên không tồn tại, resolver trả `null`.

**`getNames()`** trả tập tên có mặt trong nguồn. Nó quan trọng khi Spring cần biết liệu có field sâu hơn ở nested path để quyết định có tạo object con hay không. Với input `address.city`, `getNames()` giúp nhận diện rằng có dữ liệu của `address` ngay cả khi không có khóa độc lập tên `address`.

Ví dụ mapper phổ biến:

~~~java
static DataBinder.ValueResolver fromMap(
        Map<String, ?> input) {

    return new DataBinder.ValueResolver() {
        @Override
        public Object resolveValue(String name, Class<?> type) {
            return input.get(name);
        }

        @Override
        public Set<String> getNames() {
            return input.keySet();
        }
    };
}
~~~

Đây là **fragment của cùng ý tưởng ở mục 4**, cần import `DataBinder`, `Map` và `Set` khi tách thành file độc lập. Không cài `getNames()` bằng `Set.of()` nếu source có nested paths; như vậy binder có thể không phát hiện dữ liệu nằm dưới `address.city`.

Các điểm cần nhớ:

1. `ValueResolver` là **cách đọc input**, không phải API gọi constructor trực tiếp.
2. Đừng dùng tên Java field tùy ý nếu nguồn có key khác. Tên tham số phải được xác định đúng hoặc phải có quy tắc ánh xạ rõ ràng.
3. `resolveValue` không nên tự ý ghi dữ liệu vào object khác, thay đổi source map hoặc lưu trạng thái theo request vào singleton.
4. `getNames()` cần phản ánh tập input keys thực tế, kể cả nested/indexed keys.
5. Trong các bản Spring 6.1 đời đầu, hình dạng interface có thay đổi; ví dụ này chủ đích dùng **6.2.x**, không trộn code từ 6.1.0 với 6.2.x.

## 6. Đọc đúng đối tượng tạo được từ `getTarget()`

### 6.1. `getTarget()` trả `Object`, không trả generic `T`

`DataBinder` không phải `DataBinder<Signup>`. Vì vậy:

~~~java
Object target = binder.getTarget();

if (target instanceof Signup signup) {
    System.out.println(signup.name());
}
~~~

Đây là **fragment** dùng binder đã `construct` thành công và kiểu record `Signup` ở mục 4. Sử dụng `instanceof` pattern matching của Java 17+ để tránh ép kiểu vội.

Nếu hệ thống đã kiểm soát `targetType` và xác nhận không có lỗi, cast `Signup signup = (Signup) binder.getTarget();` cũng hợp lệ. Nhưng khi xử lý input không tin cậy, nên kiểm tra target là `null` hay không và xác nhận kiểu để có thông báo rõ ràng.

### 6.2. Thứ tự kiểm tra đáng tin cậy

~~~java
binder.construct(resolver);

BindingResult result = binder.getBindingResult();

if (result.hasErrors()) {
    // Đọc lỗi, không đưa target vào xử lý nghiệp vụ.
    return;
}

Object target = binder.getTarget();
if (!(target instanceof Signup signup)) {
    throw new IllegalStateException("Target chưa được tạo");
}

// Chỉ sử dụng signup sau khi đã kiểm tra.
~~~

Đây là **fragment**, chưa bao gồm phần khởi tạo `binder` và `resolver`. Trong chương trình ở mục 4, toàn bộ phần này đã có context đầy đủ.

**Không hiểu sai rằng `getTarget() != null` tự chứng minh dữ liệu hợp lệ.** `getTarget()` trả lời “binder đang giữ object nào?”. `BindingResult` trả lời “có lỗi binding/validation hay không?”. Một số cấu hình hoặc thời điểm lỗi có thể làm object chưa được tạo; hãy kiểm tra lỗi và target theo thứ tự rõ ràng.

### 6.3. `getBindingResult().getTarget()` và model

Trong tình huống tạo thành công:

~~~java
BindingResult result = binder.getBindingResult();
Object viaBinder = binder.getTarget();
Object viaResult = result.getTarget();

System.out.println(viaBinder == viaResult);
~~~

Đây là fragment tương ứng với ví dụ hợp lệ. Hai cách đọc trỏ tới cùng object target, nhưng **mục đích API khác nhau**: `DataBinder#getTarget()` thể hiện target binder quản lý, còn `BindingResult` cung cấp lỗi và thông tin cho quá trình binding/render view.

`BindingResult#getModel()` tạo map dành cho các tầng trình bày, thường có hai entry logic:

- khóa theo `binder.getObjectName()` chứa model attribute;
- khóa theo `BindingResult.MODEL_KEY_PREFIX + objectName` chứa chính `BindingResult`.

Ví dụ:

~~~java
Map<String, Object> model = result.getModel();
Object attribute = model.get("signup");

boolean hasErrorsEntry = model.containsKey(
        BindingResult.MODEL_KEY_PREFIX + "signup");
~~~

Đây là **fragment**, `Map` phải được import và `result` đã tồn tại. `getModel()` hữu ích trong luồng MVC/view; khi chỉ muốn đọc đối tượng vừa dựng trong một job/service, `getTarget()` rõ ràng hơn. Không giả định map model tự động là response JSON hoặc repository entity.

## 7. Nếu conversion thất bại thì sao?

Một giá trị request dạng chuỗi chưa chắc đổi được sang tham số constructor. Ví dụ `age=not-a-number` không thể chuyển thành `Integer`. Khi ấy binder có thể ghi `FieldError` vào `BindingResult` với mã thuộc nhóm `typeMismatch`.

Thử fragment riêng:

~~~java
DataBinder invalid = new DataBinder(null, "signup");
invalid.setTargetType(
        ResolvableType.forClass(Signup.class));

invalid.construct(fromMap(Map.of(
        "name", "Lan",
        "age", "not-a-number",
        "address.city", "Hue"
)));

BindingResult result = invalid.getBindingResult();
System.out.println(result.hasFieldErrors("age"));
~~~

Đây là **fragment bên trong class `ConstructDemo`** ở mục 4, sử dụng cùng record và helper. Với Spring 6.2.x và conversion mặc định, dự kiến in `true` vì `age` không thể chuyển kiểu. Không cần dựa vào nội dung thông báo lỗi cụ thể vì message code và locale có thể ảnh hưởng thông điệp hiển thị.

Để kiểm tra lỗi sâu hơn:

~~~java
result.getFieldErrors().forEach(error -> {
    System.out.println("field=" + error.getField());
    System.out.println("code=" + error.getCode());
});
~~~

Không nên trả lại `getRejectedValue()` nguyên bản cho client nếu đó có thể là mật khẩu, token, số nhận dạng hoặc dữ liệu nhạy cảm.

### Conversion error khác constructor exception

Phân biệt:

| Vấn đề | Cách xử lý |
| --- | --- |
| Chuỗi `"26"` cho `Integer age` | Binder có thể chuyển thành `26`. |
| Chuỗi `"abc"` cho `Integer age` | Xem `BindingResult`, thường có lỗi `typeMismatch`. |
| Tên tham số không khớp | Resolver có thể trả `null`; kiểm tra dữ liệu bắt buộc và chính sách validation. |
| Constructor tự ném `IllegalArgumentException` | Có thể dẫn tới `BeanInstantiationException`, không coi là FieldError thông thường. |
| Target type chưa đặt hoặc target ban đầu không null | Sai tiền điều kiện `construct`, cần sửa cách dùng API. |

Đừng hứa với người dùng rằng mọi lỗi tạo object đều nằm trong `BindingResult`: constructor có thể thất bại vì logic riêng (ví dụ kiểm tra invariant và ném exception) hoặc vì cấu hình không phù hợp. Chỉ bắt ngoại lệ tại tầng thích hợp, không nuốt lỗi rồi sử dụng một target chưa hợp lệ.

## 8. Tên tham số constructor: record, class thường và `-parameters`

Constructor binding dựa trên tên argument. Record thường phù hợp vì có canonical constructor gắn với các component (`name`, `age`, `address`).

Với class Java thông thường, hãy lưu thông tin tên tham số khi biên dịch. Một cấu hình Gradle phù hợp là:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += '-parameters'
}
~~~

Trong `build.gradle` ở mục 4, thêm đoạn này nếu build chưa có cờ trên. Một số bộ công cụ của Spring Boot đã cấu hình `-parameters`; không cần lặp khi đã có.

Một class constructor-only ví dụ:

~~~java
package demo;

public final class CreateOrder {
    private final String sku;
    private final Integer quantity;

    public CreateOrder(String sku, Integer quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    public String getSku() {
        return sku;
    }

    public Integer getQuantity() {
        return quantity;
    }
}
~~~

Đây là **tệp Java hợp lệ**, nhưng khi chạy construct cần có Spring dependency, đặt `targetType` cho `CreateOrder.class` và cung cấp các key `sku` và `quantity`. Class không cần setter. Trong trường hợp không muốn phụ thuộc `-parameters`, có thể dùng `@java.beans.ConstructorProperties({"sku", "quantity"})` trên constructor khi phù hợp với thiết kế và phiên bản.

### Khi tên HTTP khác tên Java

Spring MVC/WebFlux hỗ trợ `@BindParam` cho tên truyền vào constructor, ví dụ tên form có dấu gạch nối:

~~~java
import org.springframework.web.bind.annotation.BindParam;

public record SearchForm(
        @BindParam("search-text") String text,
        Integer page) {}
~~~

Đây là **fragment** cần đặt trong file Java đúng package và có dependency Spring Web. Với HTTP form `search-text=java`, MVC có thể ánh xạ input vào `text`.

Lưu ý: `@BindParam` trong Spring Web không phải cơ chế mặc định của **mọi** `DataBinder` được tạo thủ công. Khi tự dùng `DataBinder` như mục 4 và muốn đổi tên tham số, cấu hình `DataBinder.NameResolver` thích hợp hoặc chuẩn hóa key đưa vào resolver. Đừng mặc định chuyển `search-text` thành `text` chỉ vì trong code có annotation dành cho MVC.

## 9. Đối tượng lồng nhau, collection và indexed paths

Một điểm mạnh của constructor binding là có thể dựng **đối tượng con qua constructor của chính đối tượng đó**. Ví dụ trong `Signup`:

~~~java
public record Address(String city) {}

public record Signup(
        String name,
        Integer age,
        Address address) {}
~~~

Input không nhất thiết có sẵn một object `Address`. Chỉ cần dữ liệu đầu vào có nested key `address.city`, Spring có thể dựng `Address("Hue")` rồi truyền vào canonical constructor của `Signup`.

Với collection, cách đặt key có thể là:

~~~text
items[0].sku=BOOK
items[0].quantity=2
items[1].sku=PEN
items[1].quantity=3
~~~

Record có thể có:

~~~java
public record LineItem(String sku, Integer quantity) {}

public record Basket(java.util.List<LineItem> items) {}
~~~

Đây là **định nghĩa kiểu minh họa**, không phải chương trình chạy đầy đủ. Constructor binding của Spring hỗ trợ list/map/array qua dữ liệu dạng single-value hoặc indexed keys. Khi viết `ValueResolver` thủ công, `getNames()` phải nêu đầy đủ các key có chỉ số để framework biết nhánh nào có dữ liệu.

**Giới hạn:** không mặc định tạo collection cực lớn chỉ vì client gửi chỉ số rất lớn. Cấu hình giới hạn phù hợp với request size, collection size và Spring binder. Cơ chế auto-grow nested path của **property binding** và dựng nested object bằng **constructor binding** là hai đường xử lý khác nhau; đừng dùng `setAutoGrowNestedPaths(true)` như một cách bảo đảm mọi nested constructor đều hoạt động.

Với nested DTO bất biến, nên thiết kế constructor không có side effect và dùng các kiểu con bất biến. Nếu record chứa `List` mutable, tính bất biến chỉ là bất biến tham chiếu; cân nhắc `List.copyOf(...)` ở canonical constructor khi yêu cầu miền phù hợp.

## 10. `construct`, `bind` và `validate` không phải một thao tác

Một nhầm lẫn thường gặp là cho rằng cả ba chỉ là những tên khác nhau của “đưa dữ liệu vào object”. Thực tế:

| API | Vai trò chính | Trạng thái object |
| --- | --- | --- |
| `construct(ValueResolver)` | Chuyển input thành constructor args và tạo object | Thường bắt đầu từ target `null` |
| `bind(PropertyValues)` | Ghi property vào target đã có | Thường dùng setter/field access |
| `validate()` | Chạy các validator đã đăng ký | Cần target phù hợp để kiểm tra |
| `getBindingResult()` | Đọc lỗi và trạng thái binding | Có thể dùng sau construct/bind/validate |
| `getTarget()` | Lấy target của binder | Có thể `null` trước khi tạo hoặc sau thất bại |

Với một DTO chỉ có canonical constructor như record, thường **không cần gọi `bind(...)` sau `construct(...)`**. Property binding qua setter không tạo thêm giá trị cho record bất biến và có thể không được hỗ trợ cho những trường không có setter.

Nếu class có setter và ứng dụng chủ đích kết hợp constructor binding với property binding, Spring cho phép thiết kế như vậy. Tuy nhiên, cần giới hạn field được phép và phân biệt rõ tham số constructor bắt buộc với property tùy chọn.

### Validation không tự xuất hiện chỉ vì gọi construct

Chương trình thuần ở mục 4 tạo object; nó **không tự chạy mọi quy tắc Bean Validation** sau `construct`. Để dùng Spring `Validator` thủ công:

~~~java
DataBinder binder = new DataBinder(null, "signup");
binder.setTargetType(ResolvableType.forClass(Signup.class));

binder.construct(fromMap(inputs));

if (!binder.getBindingResult().hasErrors()
        && binder.getTarget() != null) {
    binder.addValidators(myValidator);
    binder.validate();
}

if (binder.getBindingResult().hasErrors()) {
    // Xử lý lỗi.
}
~~~

Đây là **fragment**, giả định `myValidator` là một `org.springframework.validation.Validator` hỗ trợ kiểu `Signup` và đã được tạo; `inputs` có dữ liệu như ví dụ mục 4. `validate()` chạy validator đã đăng ký, thêm lỗi vào `BindingResult`.

Trong Spring MVC, khi handler khai báo `@Valid` hoặc `@Validated` trên `@ModelAttribute`, framework có thể kích hoạt validation trong vòng đời request. **`@InitBinder`** là nơi cấu hình binder/validator trước binding, không phải lệnh gọi `construct` thủ công bên trong controller.

## 11. Trong Spring MVC: ai gọi construct và controller đọc ở đâu?

Phần lớn controller MVC **không cần tự viết**:

~~~java
DataBinder binder = new DataBinder(null);
binder.setTargetType(...);
binder.construct(...);
~~~

Spring MVC tạo và cấu hình binder khi xử lý handler argument. Với tham số `@ModelAttribute` là record, Spring có thể thực hiện constructor binding, đặt object vào argument và truyền object đã tạo cho controller.

Ví dụ fragment trong một controller:

~~~java
@PostMapping("/signups")
ResponseEntity<?> create(
        @Valid @ModelAttribute("signup") Signup form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().build();
    }

    return ResponseEntity.ok(form);
}
~~~

Đây là **fragment**, cần import `@Valid`, `@ModelAttribute`, `@PostMapping`, `ResponseEntity` và định nghĩa `Signup`, đồng thời cần Spring MVC và Bean Validation provider tương ứng nếu dùng constraint. `@Valid` chỉ có tác dụng thực tế khi DTO có constraint phù hợp.

Trong controller này, **`form` chính là đối tượng đã được Spring tạo và bind**. Controller không cần tự gọi `binder.getTarget()`. `BindingResult` phải đứng **ngay sau** tham số được kiểm tra để nhận lỗi của đúng object.

Sự tương ứng:

~~~text
Ứng dụng Java gọi DataBinder trực tiếp:
  construct(...) -> getBindingResult() -> getTarget()

Spring MVC controller:
  framework xử lý @ModelAttribute
  -> handler nhận Signup form, BindingResult errors
  -> controller đọc form/kiểm tra errors
~~~

Ngoài `@ModelAttribute`, `@RequestBody` JSON thường đi qua `HttpMessageConverter` (thường Jackson) để deserialize object. Cả hai đều có thể tạo record, nhưng **`@RequestBody` không dùng cùng đường DataBinder.construct(ValueResolver) cho form parameters**. Đừng dùng kết luận từ API constructor binding của `DataBinder` để mô tả toàn bộ JSON deserialization.

## 12. Lỗi thường gặp khi đọc target

**Quên `setTargetType`.** `new DataBinder(null)` chưa biết cần dựng class nào. Muốn `construct`, phải cấu hình `ResolvableType` trước.

**Truyền target đã tồn tại vào constructor của binder rồi lại gọi `construct`.** Lời gọi sai tiền điều kiện vì target không còn `null`. Nếu cần bind thuộc tính trên object hiện hữu, cân nhắc `bind(...)`.

**Viết `ValueResolver` thiếu `getNames()` ở Spring 6.2.** Interface cần cả hai phương thức; nếu thiếu sẽ không biên dịch. Đặc biệt với nested data, một tập tên trống còn làm việc dựng object con khó xác định.

**Sai tên constructor parameter.** Source gửi `display-name`, constructor tên `displayName`; nếu không có ánh xạ, resolver có thể trả `null`. Ghi rõ quy ước name mapping và kiểm thử thực tế.

**Gọi `getTarget()` quá sớm.** Trước `construct`, target của binder trong ví dụ là `null`. Sau đó vẫn cần kiểm tra lỗi/kiểu.

**Chỉ kiểm tra target mà không kiểm tra `BindingResult`.** Khi có lỗi chuyển kiểu, binding result là nơi chẩn đoán; không đưa object chưa được xác thực vào service.

**Cho rằng `construct` tự chạy tất cả validator.** Validation là bước riêng, cần kích hoạt theo cấu hình (ví dụ `binder.validate()` hoặc `@Valid` trong MVC).

**Nhầm record constructor binding với setter binding.** Record không có setter JavaBeans; dùng constructor để truyền tham số, không cố thêm setter để chạy `bind`.

**Không giới hạn trường đầu vào.** Constructor binding giới hạn các tham số mà constructor chấp nhận, nhưng nếu đưa `role` hay `isAdmin` vào constructor của DTO công khai, client vẫn có thể cố truyền chúng. DTO phải có đúng trường được phép; kiểm tra authorization ở service.

**Giữ DataBinder dùng chung giữa các request.** `DataBinder` giữ target, error state và cấu hình conversion; nên tạo riêng cho một lần xử lý/object, không dùng như singleton có trạng thái mutable theo request.

## 13. Kiểm tra và bài tập áp dụng

### Bài tập 1: tạo object đơn giản

Thay `Signup` thành record:

~~~java
public record ProductInput(String sku, Integer quantity) {}
~~~

Dựng `DataBinder(null, "product")`, đặt target type `ProductInput.class`, cung cấp key `sku=BOOK` và `quantity=2`, rồi gọi `construct(...)`. Kết quả mong muốn khi đọc target:

~~~text
sku=BOOK
quantity=2
~~~

Đây là đầu ra mong muốn của hai câu lệnh in giá trị, **chưa phải chương trình Java độc lập**. Bạn có thể dùng helper `fromMap(...)` từ mục 4 để tránh viết lại `ValueResolver`.

### Bài tập 2: lỗi conversion

Đổi `quantity=2` thành `quantity=two`. Sau `construct(...)`, dùng:

~~~java
BindingResult result = binder.getBindingResult();
System.out.println(result.hasFieldErrors("quantity"));
~~~

Kiểm tra lỗi thay vì ép kiểu/đọc target ngay. Nếu muốn hiển thị đầy đủ, lặp `result.getFieldErrors()` và in tên field/mã lỗi.

### Bài tập 3: nested record

Tạo `Delivery(String recipient, Address address)` và thử hai key `recipient=An`, `address.city=DaNang`. Kiểm tra `ValueResolver.getNames()` có đúng cả hai key. Kết quả kỳ vọng là một `Delivery` có `address` khác `null` và thành phần `city` tương ứng.

### Checklist trước khi dùng trong ứng dụng

- `DataBinder` được tạo với target `null`.
- `setTargetType(...)` mô tả đúng class đích.
- Kiểu đích có data constructor rõ ràng, tên tham số có thể được đọc hoặc được ánh xạ.
- `ValueResolver.resolveValue(...)` và `getNames()` phản ánh đúng source.
- Chuyển kiểu và nested paths được kiểm thử.
- Sau `construct(...)`, đọc `BindingResult` trước khi dùng `getTarget()`.
- Cast/kiểm tra target an toàn, tránh dùng object null.
- Validation được chạy riêng khi cần, còn DTO và service kiểm soát field/phân quyền.

## 14. Ghi nhớ

Trong Spring Framework 6.2.x, cách dùng `DataBinder` cho constructor binding có trình tự rõ ràng:

~~~text
new DataBinder(null, objectName)
  -> setTargetType(ResolvableType.forClass(Target.class))
  -> construct(ValueResolver)
  -> getBindingResult() để kiểm tra lỗi
  -> getTarget() để lấy object tạo thành công
~~~

`construct` làm nhiệm vụ **dựng target**, `getTarget` **đọc target**, `getBindingResult` **cho biết có thể tin tưởng kết quả binding đến đâu**. Ba thao tác này nên được hiểu cùng nhau, đặc biệt khi dữ liệu đến từ form hoặc một nguồn bên ngoài không tin cậy.

### Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Data Binding và Constructor Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation/data-binding.html)
- [DataBinder API (Spring Framework 6.2)](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/DataBinder.html)
- [DataBinder.ValueResolver API (Spring Framework 6.2)](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/DataBinder.ValueResolver.html)
- [Spring MVC — @ModelAttribute argument](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
