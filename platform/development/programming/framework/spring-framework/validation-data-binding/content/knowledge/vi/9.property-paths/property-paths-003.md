# Khóa Map dạng `attributes[key]` trong đường dẫn thuộc tính Spring

Trong Spring Framework, một trường đầu vào có tên **`attributes[color]`** có thể được bind vào một đối tượng Java chứa thuộc tính `Map` tên `attributes`. Phần nằm trong dấu ngoặc vuông là **khóa của Map**, không phải tên một thuộc tính JavaBean mới. Đây là một dạng **property path** được `BeanWrapper` và `DataBinder` hỗ trợ.

Ví dụ, nếu đối tượng đích có:

~~~java
private Map<String, String> attributes = new LinkedHashMap<>();
~~~

và nguồn dữ liệu form chứa cặp:

~~~text
attributes[color] = blue
~~~

thì kết quả mong đợi sau property binding hợp lệ tương đương:

~~~java
form.getAttributes().put("color", "blue");
~~~

Để dùng đúng cú pháp này, cần hiểu rõ cách Spring phân tích đường dẫn, phân biệt `Map` với `List` hoặc bean lồng nhau, chuyển đổi kiểu của giá trị, xử lý lỗi và giới hạn những khóa được phép ghi. Nội dung dưới đây tập trung vào **Spring Framework Data Binding và đường dẫn thuộc tính**; hành vi của JSON deserialization và Spring Boot `@ConfigurationProperties` được phân biệt riêng vì chúng sử dụng cơ chế khác.

## 1. Phân tích một đường dẫn `attributes[key]`

Cấu trúc khái quát:

~~~text
attributes[key]
│          │
│          └── khóa dùng để truy cập phần tử trong Map
└───────────── tên thuộc tính JavaBean của object đích
~~~

Giả sử có lớp:

~~~java
public class ProductForm {
    private Map<String, String> attributes = new LinkedHashMap<>();

    public Map<String, String> getAttributes() {
        return attributes;
    }

    public void setAttributes(Map<String, String> attributes) {
        this.attributes = attributes;
    }
}
~~~

Khi Spring bind tên trường `attributes[color]` cùng giá trị `blue` vào `ProductForm`, nó tìm thuộc tính `attributes` qua JavaBean getter/setter rồi truy cập phần tử Map có khóa `"color"`. Kết quả:

~~~text
ProductForm
  attributes:
    color -> "blue"
~~~

Nếu có thêm `attributes[size]=L` và `attributes[origin]=VN`:

~~~text
ProductForm
  attributes:
    color  -> "blue"
    size   -> "L"
    origin -> "VN"
~~~

Chú ý: ký hiệu `key` trong đề bài là **vị trí điền khóa cụ thể**. Trong `attributes[key]`, Spring sẽ dùng khóa có tên đúng là `"key"` nếu input thực sự ghi chữ `key`. Nó không tự tìm một biến Java tên `key`.

### So sánh các kiểu đường dẫn

| Property path | Loại đối tượng phù hợp | Ý nghĩa |
| --- | --- | --- |
| `name` | JavaBean | Thuộc tính `name` của bean. |
| `address.city` | Bean có thuộc tính object `address` | Truy cập thuộc tính `city` trên bean lồng nhau. |
| `items[0]` | `List` hoặc array | Phần tử có chỉ số 0. |
| `attributes[color]` | `Map` | Phần tử có khóa `"color"`. |
| `attributes[0]` | `Map` | Phần tử theo **khóa** 0, với kiểu khóa được xác định theo khai báo Map; không mặc nhiên là phần tử thứ nhất. |
| `attributes[home].city` | `Map` có giá trị là bean | Truy cập `city` của object ứng với khóa `"home"`, nếu đường dẫn và object trung gian hợp lệ. |

Spring `BeanWrapper` quy ước `accounts[KEY]` để chỉ phần tử Map, còn `accounts[2]` có thể là phần tử thứ ba của một danh sách/array khi loại thuộc tính tương ứng là một collection được đánh chỉ số. **Dấu ngoặc vuông không tự quyết định kiểu cấu trúc; kiểu khai báo của thuộc tính mới quyết định đó là index hay Map key.**

Đừng đồng nhất `attributes.color` với `attributes[color]`. Dấu chấm bình thường dùng cho **thuộc tính lồng nhau**; dấu ngoặc vuông dùng để đi vào **entry của Map**. Với `Map<String, String>`, tên `color` là khóa, không phải một getter `getColor()` của Map.

## 2. Spring xử lý cú pháp này qua những bước nào?

Với setter/property binding, luồng điển hình là:

~~~text
Dữ liệu form hoặc tập PropertyValues
    "attributes[color]" = "blue"
                 |
                 v
            DataBinder
                 |
                 v
        BeanWrapper/property accessor
                 |
       Phân tích path + kiểm tra thuộc tính
                 |
      target.getAttributes() -> Map
                 |
         xác định khóa "color"
                 |
           chuyển kiểu giá trị
                 |
         map.put("color", "blue")
                 |
                 v
         BindingResult (nếu có lỗi)
~~~

Ví dụ API cốt lõi:

~~~java
ProductForm form = new ProductForm();

DataBinder binder = new DataBinder(form, "product");
MutablePropertyValues values = new MutablePropertyValues();
values.add("attributes[color]", "blue");
values.add("attributes[size]", "L");

binder.bind(values);

BindingResult result = binder.getBindingResult();
if (result.hasErrors()) {
    // Trả lỗi binding, chưa sử dụng dữ liệu để ghi vào hệ thống.
} else {
    String color = form.getAttributes().get("color");
}
~~~

Đoạn trên minh họa các lệnh của Spring; những `import` cần thiết gồm `org.springframework.validation.DataBinder`, `org.springframework.validation.BindingResult` và `org.springframework.beans.MutablePropertyValues`. Một dự án Maven đầy đủ được cung cấp ở mục 4.

Các điều kiện quan trọng:

1. `ProductForm` phải bộc lộ thuộc tính `attributes` phù hợp với cơ chế truy cập JavaBeans. Dùng getter/setter đúng kiểu giúp Spring đọc metadata của Map và chuyển đổi giá trị.
2. Với setter/property binding, Map nên là một collection **mutable** đã khởi tạo như `LinkedHashMap`, hoặc được tạo theo cơ chế auto-grow được hỗ trợ. Một Map bất biến từ `Map.of(...)` không phù hợp để Spring thêm entry.
3. `DataBinder` phải nhận tên trường **chính xác**, bao gồm dấu ngoặc. Với raw form, tên input `attributes[color]` là tên field thực tế.
4. Binder có thể cập nhật một số entry thành công ngay cả khi entry khác bị lỗi. Vì vậy phải kiểm tra `getBindingResult()` trước khi sử dụng object cho nghiệp vụ.
5. `DataBinder.bind(...)` thực hiện bind/chuyển đổi. Nếu muốn ràng buộc logic bổ sung, cần đăng ký validator rồi gọi `binder.validate()` trong luồng thủ công.

### Tại sao nên khởi tạo Map?

~~~java
private Map<String, String> attributes = new LinkedHashMap<>();
~~~

Cách khởi tạo này khiến đường dẫn `attributes[color]` có một Map có thể thay đổi ngay từ đầu, dễ kiểm tra và kiểm thử. Spring có khả năng tự tạo một số cấu trúc trung gian qua `autoGrowNestedPaths` trong điều kiện phù hợp, nhưng việc phụ thuộc hoàn toàn vào auto-grow có thể thay đổi theo kiểu khai báo, accessor và cấu hình binder. Với input DTO phục vụ form, **khởi tạo Map mutable rõ ràng** thường dễ hiểu hơn.

Nếu đối tượng có:

~~~java
private Map<String, String> attributes = Map.of();
~~~

thì việc thêm khóa mới không được Map bất biến chấp nhận. Có thể dẫn tới lỗi trong quá trình binding; đừng giả định kết quả luôn giống như `LinkedHashMap`.

## 3. Kiểu khóa và kiểu giá trị trong Map

Một khai báo `Map<K, V>` cung cấp hai loại thông tin:

- `K` quyết định cách hiểu và có thể chuyển đổi phần trong ngoặc vuông.
- `V` quyết định kiểu mà Spring cần gán cho giá trị nhập vào.

Ví dụ:

~~~java
private Map<String, String> attributes = new LinkedHashMap<>();
~~~

`attributes[color]=blue` tạo entry có khóa `String "color"`, giá trị `String "blue"`.

Với:

~~~java
private Map<String, Integer> attributes = new LinkedHashMap<>();
~~~

`attributes[stock]=12` cần chuyển giá trị đầu vào `"12"` sang `Integer 12`. Nếu request gửi `attributes[stock]=abc`, conversion sang số có thể thất bại và tạo một `FieldError` trong `BindingResult` mang field path `attributes[stock]` cùng mã lỗi như `typeMismatch`.

Nếu kiểu khóa là `Map<Long, String>`, cú pháp `attributes[42]` có thể dẫn tới việc chuyển khóa thành `Long` theo metadata generic và bộ converter đã cấu hình. Với kiểu khóa đặc thù, cần converter/editor thích hợp; không thể xem mọi chuỗi trong ngoặc như một String một cách bất biến.

### Nếu Map chứa object thay vì chuỗi

Ví dụ:

~~~java
public class Contact {
    private String city;

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}

public class ContactForm {
    private Map<String, Contact> attributes = new LinkedHashMap<>();

    public Map<String, Contact> getAttributes() {
        return attributes;
    }

    public void setAttributes(Map<String, Contact> attributes) {
        this.attributes = attributes;
    }
}
~~~

Khi đó `attributes[home].city=Hanoi` có nghĩa:

~~~java
form.getAttributes().get("home").setCity("Hanoi");
~~~

Đây là **một đường dẫn lồng nhau**: để hoạt động, entry `"home"` cần chứa `Contact` hợp lệ hoặc accessor phải có khả năng tạo đối tượng trung gian. Trong ứng dụng cần kiểm soát chặt, có thể khởi tạo `attributes.put("home", new Contact())` trước khi bind để loại bỏ sự mơ hồ. Nếu entry là `null` hoặc không có setter/constructor phù hợp và không thể auto-grow, binder có thể ghi nhận lỗi hoặc ném exception tùy tình huống.

Không nhầm cú pháp `attributes[home].city` với một Map có khóa nguyên văn `"home.city"`. Hai trường hợp lưu dữ liệu hoàn toàn khác nhau.

## 4. Ví dụ Java 17+ hoàn chỉnh: bind Map, xử lý lỗi và khóa không cho phép

Chương trình sau dùng **Spring Framework 6.2**, tạo một input DTO có `Map<String, Integer>` tên `attributes`. Hai khóa nghiệp vụ hợp lệ là `stock` và `threshold`. Có ba tình huống:

- **valid**: hai entry chuyển sang `Integer` thành công.
- **invalid**: `stock=abc` sai kiểu, `threshold=-1` sai quy tắc; đồng thời client cố thêm khóa không được phép `admin`.
- **suppressedOnly**: cả hai giá trị hợp lệ nhưng client vẫn gửi `admin`.

Chương trình dùng `setAllowedFields(...)` để giới hạn khóa, `Validator` để kiểm tra giá trị, `BindingResult` để đọc lỗi và danh sách `suppressedFields` để ra quyết định tiếp tục.

Cấu trúc thư mục:

~~~text
map-property-path/
├── pom.xml
└── src/main/java/example/MapPropertyPathDemo.java
~~~

Tạo `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>map-property-path</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                    <mainClass>example.MapPropertyPathDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tạo `src/main/java/example/MapPropertyPathDemo.java`:

~~~java
package example;

import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeMap;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.Validator;

public class MapPropertyPathDemo {

    public static final class ProductForm {
        private Map<String, Integer> attributes = new LinkedHashMap<>();

        public Map<String, Integer> getAttributes() {
            return attributes;
        }

        public void setAttributes(Map<String, Integer> attributes) {
            this.attributes = attributes;
        }
    }

    public static final class ProductValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return ProductForm.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            ProductForm form = (ProductForm) target;
            Integer stock = form.getAttributes().get("stock");
            Integer threshold = form.getAttributes().get("threshold");

            // Đừng ghi lỗi giá trị trùng với lỗi conversion của cùng path.
            if (!errors.hasFieldErrors("attributes[stock]")
                    && (stock == null || stock < 0)) {
                errors.rejectValue(
                        "attributes[stock]", "stock.nonNegative",
                        "Stock phải là số không âm");
            }

            if (!errors.hasFieldErrors("attributes[threshold]")
                    && (threshold == null || threshold < 0)) {
                errors.rejectValue(
                        "attributes[threshold]", "threshold.nonNegative",
                        "Threshold phải là số không âm");
            }
        }
    }

    private static String code(BindingResult result, String key) {
        FieldError error = result.getFieldError("attributes[" + key + "]");
        return error == null ? "none" : error.getCode();
    }

    private static void run(
            String label, String stock, String threshold,
            boolean sendAdmin) {

        ProductForm form = new ProductForm();
        DataBinder binder = new DataBinder(form, "product");
        binder.setAllowedFields(
                "attributes[stock]", "attributes[threshold]");
        binder.setValidator(new ProductValidator());

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("attributes[stock]", stock);
        values.add("attributes[threshold]", threshold);

        if (sendAdmin) {
            values.add("attributes[admin]", "999");
        }

        binder.bind(values);
        binder.validate();

        BindingResult result = binder.getBindingResult();

        System.out.println(label + " map="
                + new TreeMap<>(form.getAttributes()));
        System.out.println(label + " errors=" + result.getErrorCount()
                + ", stockError=" + code(result, "stock")
                + ", thresholdError=" + code(result, "threshold"));
        System.out.println(label + " suppressed="
                + Arrays.toString(result.getSuppressedFields()));

        boolean proceed = !result.hasErrors()
                && result.getSuppressedFields().length == 0;
        System.out.println(label + " proceed=" + proceed);
    }

    public static void main(String[] args) {
        run("valid", "12", "4", false);
        run("invalid", "abc", "-1", true);
        run("suppressedOnly", "7", "2", true);
    }
}
~~~

Tại thư mục `map-property-path`, dùng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java
~~~

Những dòng chương trình in ra:

~~~text
valid map={stock=12, threshold=4}
valid errors=0, stockError=none, thresholdError=none
valid suppressed=[]
valid proceed=true
invalid map={threshold=-1}
invalid errors=2, stockError=typeMismatch, thresholdError=threshold.nonNegative
invalid suppressed=[attributes[admin]]
invalid proceed=false
suppressedOnly map={stock=7, threshold=2}
suppressedOnly errors=0, stockError=none, thresholdError=none
suppressedOnly suppressed=[attributes[admin]]
suppressedOnly proceed=false
~~~

Giải thích:

1. Các trường `attributes[stock]` và `attributes[threshold]` được binder phân tích thành khóa của Map và chuyển giá trị chuỗi sang `Integer` nhờ metadata generic.
2. Ở trường hợp `invalid`, `attributes[stock]=abc` gây lỗi chuyển kiểu. Entry tương ứng không nhận được số hợp lệ. `attributes[threshold]=-1` bind thành công nhưng validator ghi thêm lỗi theo path `attributes[threshold]`.
3. Client cố gán `attributes[admin]`, nhưng `setAllowedFields(...)` chỉ cho phép hai đường dẫn khác. Spring loại bỏ field bị cấm và ghi tên nó vào `getSuppressedFields()`.
4. Ở `suppressedOnly`, `hasErrors()` vẫn là `false` dù có field bị chặn. Chương trình chọn chính sách **từ chối mọi request chứa suppressed fields**, nên `proceed=false`.
5. `TreeMap` chỉ dùng **khi in output**, để thứ tự khóa ổn định; DTO vẫn dùng `LinkedHashMap`. Không lấy thứ tự duyệt Map làm logic nghiệp vụ.

Đây là chương trình **không cần Spring Boot hay server HTTP**. Phần kết quả trên là stdout của logic minh họa; bản demo không kết nối database hoặc gọi service thực tế.

## 5. Đọc lỗi đúng đường dẫn Map

`BindingResult` lưu lỗi theo tên field/property path, bao gồm phần ngoặc:

~~~java
BindingResult result = binder.getBindingResult();

FieldError stockError =
        result.getFieldError("attributes[stock]");

if (stockError != null) {
    String field = stockError.getField();    // "attributes[stock]"
    String code = stockError.getCode();      // ví dụ "typeMismatch"
    Object rejected = stockError.getRejectedValue();
}
~~~

Đối với validation thủ công, dùng `errors.rejectValue(...)` với chính property path:

~~~java
errors.rejectValue(
        "attributes[threshold]",
        "threshold.nonNegative",
        "Threshold phải là số không âm");
~~~

Đoạn này đặt trong phương thức `validate(Object target, Errors errors)` của `Validator`. Nếu muốn kiểm tra nhiều khóa của Map, có thể duyệt qua các entry phù hợp và ghi lỗi cho từng đường dẫn; trước khi làm vậy, phải giới hạn hoặc kiểm tra khóa, tránh tạo field path không an toàn từ chuỗi không tin cậy.

Lỗi mức object (ví dụ hai giá trị trong Map mâu thuẫn nhau) có thể ghi bằng `errors.reject(...)`; không bắt buộc ép mọi quy tắc liên trường thành lỗi của một khóa.

### Giá trị trên target khác giá trị bị từ chối

Giả sử `attributes[stock]` hiện có `10`, request gửi `abc`. Sau conversion thất bại, target có thể vẫn còn giá trị cũ của entry, trong khi `FieldError.getRejectedValue()` lưu `"abc"` để giao diện hiển thị lại. Vì vậy:

- `form.getAttributes().get("stock")` phản ánh object hiện tại.
- `result.getFieldError("attributes[stock]")` phản ánh lỗi tương ứng.
- `result.getFieldValue("attributes[stock]")` có thể ưu tiên giá trị bị từ chối trong trường hợp render form.

**Không chỉ đọc Map rồi coi request đã hợp lệ**. Khi có lỗi, một số entry khác đã được bind, nhưng không được cho phép nghiệp vụ ghi trạng thái không nhất quán.

### Dữ liệu đầu vào thiếu một khóa

Nếu không có `attributes[stock]` trong input, binder thông thường sẽ không tự tạo entry đó chỉ vì DTO khai báo `Map<String, Integer>`. Ở trường hợp create, validator cần kiểm tra:

~~~java
Integer stock = form.getAttributes().get("stock");
if (stock == null) {
    errors.rejectValue(
            "attributes[stock]",
            "stock.required",
            "Thiếu stock");
}
~~~

Lưu ý `Map.get(...) == null` không luôn phân biệt **khóa không tồn tại** với **khóa có giá trị null**. Nếu hai trạng thái có ý nghĩa khác nhau, dùng `containsKey("stock")` hoặc thêm thông tin hiện diện từ request. Với PATCH, cả việc không gửi một entry, gửi entry là null và gửi giá trị thực có thể cần ba nhánh khác nhau.

## 6. Trường hợp khóa có ký tự đặc biệt

Với khóa đơn giản như `color`, `stock` và `region`, cú pháp:

~~~text
attributes[color]
attributes[stock]
attributes[region]
~~~

là trực tiếp nhất.

Nếu khóa có dấu chấm hoặc ký tự khiến người đọc nhầm với thuộc tính lồng nhau, Spring BeanWrapper hỗ trợ token khóa đặt trong dấu nháy, ví dụ:

~~~text
attributes['display.name']
attributes["support.email"]
~~~

Ý định là lấy **nguyên khóa** `"display.name"` hoặc `"support.email"` của Map. Việc đặt khóa trong ngoặc giúp phân biệt nó với dạng `attributes[display].name` (truy cập thuộc tính `name` của object nằm dưới khóa `display`).

Khi dùng form HTML, tên field thực tế có thể là:

~~~html
<input type="text"
       name="attributes['display.name']"
       value="Tên hiển thị">
~~~

Browser sẽ mã hóa ký tự đặc biệt khi gửi `application/x-www-form-urlencoded`; Spring xử lý tên tham số sau khi server đã decode. Với các khóa phức tạp chứa ngoặc vuông, dấu nháy hoặc những ký tự đặc biệt khó biểu diễn an toàn trong property path, nên thiết kế một API nhận **Map JSON** hoặc một danh sách các cặp key/value rồi xác thực khóa rõ ràng, thay vì ghép chuỗi property path tùy ý.

**Không nhầm với Spring Boot `@ConfigurationProperties`.** Cơ chế *relaxed binding* cấu hình ngoài của Spring Boot có quy tắc riêng về tên thuộc tính và khóa Map. Bài này đang nói về đường dẫn JavaBean của **Spring Framework `BeanWrapper`/`DataBinder`**.

## 7. Tích hợp với Spring MVC: form khác JSON

### 7.1. Form HTML hoặc query parameters với `@ModelAttribute`

Một form có thể gửi:

~~~html
<form method="post" action="/products">
    <label>
        Stock
        <input name="attributes[stock]" value="12">
    </label>
    <label>
        Threshold
        <input name="attributes[threshold]" value="4">
    </label>
    <button type="submit">Gửi</button>
</form>
~~~

Spring MVC `WebDataBinder` có thể bind những tên tham số trên vào `Map` của DTO `@ModelAttribute`. Đoạn controller minh họa:

~~~java
// Đoạn trích Spring MVC; ProductForm và productService
// thuộc ứng dụng thực tế, không phải file chạy độc lập.
@PostMapping("/products")
public String create(
        @Valid @ModelAttribute("product") ProductForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return "products/new";
    }

    productService.create(form.getAttributes());
    return "redirect:/products";
}
~~~

`BindingResult` phải đứng ngay sau tham số `@ModelAttribute` tương ứng. Nếu sử dụng `@Valid` thì cần validator/Bean Validation provider phù hợp để ràng buộc thực sự chạy. Nếu request còn phải tuân thủ chính sách khóa cho phép, cần cấu hình binder và xử lý suppressed fields theo contract thay vì chỉ kiểm tra `hasErrors()`.

Ví dụ cấu hình binder cho controller:

~~~java
// Đoạn trích trong cùng @Controller hoặc @ControllerAdvice.
@InitBinder("product")
void configureProduct(WebDataBinder binder) {
    binder.setAllowedFields(
            "attributes[stock]", "attributes[threshold]");
}
~~~

`WebDataBinder` là lớp con của `DataBinder` dành cho ngữ cảnh web. `setAllowedFields` được áp dụng cho **property binding** của request, bảo vệ khỏi việc người dùng tự thêm những đường dẫn ngoài phạm vi dự kiến.

### 7.2. JSON body với `@RequestBody`

JSON thường biểu diễn Map bằng một object lồng nhau:

~~~json
{
  "attributes": {
    "stock": 12,
    "threshold": 4
  }
}
~~~

Khi controller nhận `@RequestBody ProductForm form`, Jackson đọc JSON để tạo object Java. Trong trường hợp này, JSON không cần mang khóa văn bản `"attributes[stock]"`. Đường đi là **JSON property `attributes` -> JSON object keys -> Map entries**, thông qua deserializer, không phải việc Spring `BeanWrapper` phân tích chuỗi field name có ngoặc.

Hai mẫu wire format khác nhau:

| Dữ liệu đến | Cơ chế thông dụng | Tên được hiểu |
| --- | --- | --- |
| Form/query: `attributes[stock]=12` | Spring MVC property binding (`WebDataBinder`) | Path `attributes[stock]`. |
| JSON: `{"attributes":{"stock":12}}` | JSON deserialization (thường Jackson) | Property `attributes` chứa Map key `stock`. |
| JSON: `{"attributes[stock]":12}` | JSON deserialization thông thường | Một JSON property tên nguyên văn `attributes[stock]`; **không mặc định** được BeanWrapper phân tích thành Map entry. |

Không dùng một thử nghiệm JSON để kết luận setter/property binding của form hoạt động ra sao. Mỗi đường nhận dữ liệu cần test riêng.

## 8. Giới hạn những khóa Map được phép bind

Vì `attributes[key]` cho phép client cung cấp tên khóa động, nó cần được đối xử như **dữ liệu không tin cậy**. Nguy cơ không chỉ nằm ở giá trị; chính **key** cũng có thể kích hoạt hành vi không mong muốn của ứng dụng, chẳng hạn ghi đè một thuộc tính cấu hình, thêm metadata đặc quyền hoặc làm Map tăng kích thước quá mức.

### 8.1. Khi tập khóa được biết trước

Ưu tiên whitelist cụ thể:

~~~java
binder.setAllowedFields(
        "attributes[stock]",
        "attributes[threshold]");
~~~

Nếu client gửi `attributes[admin]`, field đó sẽ bị suppression. Đọc lại:

~~~java
String[] suppressed = binder.getBindingResult()
        .getSuppressedFields();

if (suppressed.length > 0) {
    // Ví dụ: từ chối request do chứa field ngoài hợp đồng.
}
~~~

`getSuppressedFields()` là **tín hiệu riêng**; nó không tự đảm bảo `hasErrors()` sẽ bằng true. Từ chối hay bỏ qua field bị chặn là quyết định của ứng dụng. Đối với request nhạy cảm, từ chối thường làm hành vi rõ ràng và dễ kiểm thử hơn.

### 8.2. Khi nghiệp vụ thực sự cần khóa động

Có thể sử dụng pattern có wildcard trong `allowedFields` khi được phép bind nhiều khóa, nhưng phải hiểu **wildcard mở rộng bề mặt đầu vào**. Ví dụ pattern `attributes*` có thể khớp nhiều property path bắt đầu bằng `attributes`, rộng hơn một tập khóa hữu hạn. Ngay cả pattern dạng `attributes[*]` cũng không thay thế quy tắc xác thực tên khóa và giới hạn loại/độ dài nội dung.

Nếu cho phép tùy biến metadata, thiết kế một contract rõ:

- Tên khóa dài tối đa bao nhiêu ký tự, thuộc bảng chữ hoặc biểu thức cho phép nào?
- Bao nhiêu entry tối đa trong một request?
- Giá trị giới hạn độ dài, kiểu dữ liệu, khoảng số, hoặc tập lựa chọn ra sao?
- Khóa nào thuộc hệ thống và **không bao giờ** do client ghi?
- Trùng khóa trong request form/JSON sẽ được xử lý theo contract nào?
- Liệu người dùng có quyền cập nhật metadata của đúng đối tượng đang thao tác?

Với dữ liệu quan trọng, DTO riêng cho đầu vào và ánh xạ thủ công sang domain entity thường an toàn hơn việc bind mọi thuộc tính của entity.

## 9. Validation Map và entry lồng nhau

Một Map có thể cần kiểm tra cả **danh sách key** lẫn **giá trị của từng entry**.

Với custom Spring `Validator`, có thể kiểm tra giá trị và báo lỗi theo đường dẫn:

~~~java
@Override
public void validate(Object target, Errors errors) {
    ProductForm form = (ProductForm) target;
    Integer stock = form.getAttributes().get("stock");

    if (!errors.hasFieldErrors("attributes[stock]")
            && (stock == null || stock < 0)) {
        errors.rejectValue(
                "attributes[stock]",
                "stock.nonNegative",
                "Stock phải là số không âm");
    }
}
~~~

Đoạn này được đặt trong một lớp `implements Validator` có `supports(...)` tương ứng. Kiểm tra `hasFieldErrors(...)` trước khi tạo lỗi số lượng giúp tránh chồng thông báo nghiệp vụ lên lỗi chuyển kiểu đã được binder ghi nhận.

Với **Jakarta Bean Validation**, có thể khai báo ràng buộc container element, chẳng hạn:

~~~java
// Đoạn minh họa. Cần provider Jakarta Bean Validation
// và cơ chế kích hoạt validation thích hợp.
private Map<
        @jakarta.validation.constraints.Pattern(
                regexp = "[a-z][a-z0-9_-]{0,31}") String,
        @jakarta.validation.constraints.NotBlank String
        > attributes = new LinkedHashMap<>();
~~~

Điều này kiểm tra những key/value mà provider nhìn thấy trong Map **sau khi đối tượng đã được tạo/bind**, tùy phiên bản và cách cấu hình Bean Validation. Ràng buộc container element không tự thay thế whitelist hoặc giới hạn tổng số entry. Nếu input có lỗi chuyển kiểu thì vẫn phải đọc `BindingResult` của binder; Bean Validation không giải mã lại những chuỗi đã không thể bind.

Với `Map<String, Contact>`, để ràng buộc cascade vào từng object `Contact`, có thể sử dụng ràng buộc `@Valid` trên value type hoặc cấu hình tương đương, đi kèm Bean Validation provider. Trong Spring MVC, chú ý đường dẫn lỗi mà framework trả về để hiển thị đúng entry form.

## 10. Những lỗi phổ biến

1. **Dùng dấu chấm thay cho dấu ngoặc:** `attributes.color` thường diễn giải như đường dẫn lồng nhau, còn `attributes[color]` truy cập Map key `color`. Đừng tự xem chúng tương đương.
2. **Quên getter/setter hoặc dùng Map bất biến:** Binder cần truy cập được thuộc tính và có đích có thể cập nhật. Ưu tiên DTO rõ ràng với Map mutable.
3. **Cho rằng số trong ngoặc luôn là chỉ số:** `items[0]` trên List khác `attributes[0]` trên Map; kiểu key của Map và converter quyết định ý nghĩa.
4. **Không kiểm tra lỗi conversion:** `attributes[stock]=abc` không được biến thành số hợp lệ. Target có thể đã thay đổi một phần; luôn đọc `BindingResult` trước nghiệp vụ.
5. **Bỏ qua `getSuppressedFields()`:** Key ngoài allowlist có thể bị loại nhưng không sinh field error. Xử lý theo chính sách rõ ràng.
6. **Tin rằng Map không bao giờ bị null:** Nếu constructor, setter hoặc dữ liệu khác thay thế Map bằng `null`, các thao tác truy cập trực tiếp có thể lỗi. Thiết kế DTO và binder nhất quán.
7. **Dùng JSON body có tên literal `attributes[color]` rồi mong Spring tự tách key:** JSON deserializer thường xử lý tên property theo cấu trúc JSON, không theo đường dẫn `BeanWrapper` của form.
8. **Không kiểm soát số lượng và tên khóa động:** Client có thể gửi nhiều entry hoặc key kỳ lạ. Whitelist hoặc validate cả key và số lượng entry.
9. **Bind trực tiếp entity có dữ liệu hệ thống:** Khi Map thuộc entity nhạy cảm, client có thể tác động entry không thuộc quyền của họ. Dùng DTO chỉ gồm field công khai, allowlist và kiểm tra quyền tại service.
10. **Nhầm hai loại Map:** `MutablePropertyValues` giữ các **tên property path làm khóa đầu vào**, còn `form.getAttributes()` là **Map nghiệp vụ sau khi parse path**. Cặp `"attributes[color]" -> "blue"` ở phía `MutablePropertyValues` không được đưa nguyên vào `form.getAttributes()` như khóa `"attributes[color]"`.

## 11. Test tối thiểu cần có

Nên kiểm tra hành vi trên điểm nhận dữ liệu thực tế, không chỉ kiểm tra getter:

| Test case | Dữ liệu | Điều cần xác minh |
| --- | --- | --- |
| Key String hợp lệ | `attributes[color]=blue` | `attributes.get("color")` là `"blue"`. |
| Nhiều key | `attributes[color]=blue`, `attributes[size]=L` | Hai entry độc lập, không tạo bean property tên `color`. |
| Kiểu giá trị số | `attributes[stock]=12` với `Map<String,Integer>` | Giá trị là `Integer 12` sau conversion. |
| Conversion lỗi | `attributes[stock]=abc` | `BindingResult` có lỗi trên path `attributes[stock]`; không gọi service ghi dữ liệu. |
| Field không cho phép | `attributes[admin]=999` | Không cập nhật khóa `admin`; `getSuppressedFields()` phản ánh việc loại bỏ. |
| Khóa có dấu chấm | `attributes['display.name']=x` | Khóa mong đợi là `"display.name"`, cần test với binder/version đang chạy. |
| Nested object | `attributes[home].city=Hanoi` | Object ở khóa `home` được cập nhật khi đường dẫn và object trung gian hợp lệ. |
| Thiếu entry | Không gửi `attributes[stock]` | Kiểm tra luật bắt buộc nhập và phản hồi đúng contract. |
| JSON khác form | JSON object con ở `attributes` | Jackson tạo đúng Map; không đòi cú pháp ngoặc ở JSON key. |
| Quá nhiều/khóa bị cấm | Nhiều key tùy ý | Validator/allowlist/giới hạn request từ chối hoặc xử lý như quy định. |

Trong kiểm thử controller/service, ngoài thông báo lỗi còn nên xác minh **không có side effect** đối với request sai kiểu hoặc khóa bị cấm. Ví dụ dùng Mockito xác minh service không được gọi khi `BindingResult.hasErrors()` hoặc khi chính sách suppressed field bị vi phạm.

## 12. Quy tắc ghi nhớ

Cách đọc chính xác của `attributes[key]` là: **tìm property `attributes` trên object đích; truy cập Map bằng khóa `key`; chuyển đổi và gán giá trị vào entry đó**. Kiểu `Map<K,V>` quyết định kiểu khóa, kiểu giá trị; `BeanWrapper`/`DataBinder` thực hiện truy cập đường dẫn và chuyển đổi trong property binding.

Với input đến từ người dùng, cần kết hợp:

- **DTO riêng có Map mutable và tên trường rõ ràng** để binder truy cập an toàn.
- **`BindingResult`** để xử lý lỗi bind/validation, bao gồm path ở dạng `attributes[key]`.
- **`setAllowedFields(...)`**, kiểm tra `getSuppressedFields()` và xác thực key/value để chặn thao tác không được phép.
- **Phân biệt form `@ModelAttribute` với JSON `@RequestBody`**, vì cách chuyển đổi đường dẫn khác nhau.
- **Kiểm tra nghiệp vụ ở service** sau khi đầu vào đã đạt yêu cầu; không tự coi việc Map đã có entry là đủ để thực hiện giao dịch.

### Tài liệu Spring chính thức

- [Spring Framework — Data Binding và BeanWrapper](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring MVC — Data Binding và thiết kế model an toàn](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring MVC — `@ModelAttribute` arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — `DataBinder` API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework — `BindingResult` API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/validation/BindingResult.html)
