# Khởi tạo DataBinder với target null và thiết lập targetType để gắn qua constructor

## 1. Vấn đề: binding khi chưa có đối tượng đích

Trong property binding truyền thống, ứng dụng đã có một object, tạo `DataBinder` với object đó, sau đó gọi `bind(PropertyValues)` để gán dữ liệu thông qua properties. Với **constructor binding**, object đích có thể **chưa tồn tại**: dữ liệu đầu vào sẽ được chuyển thành các constructor arguments để Spring gọi constructor và tạo object.

Spring Framework 6.1+ hỗ trợ API `DataBinder.construct(ValueResolver)` cùng `setTargetType(ResolvableType)` nhằm mô tả chính xác kiểu đích khi binder được tạo với `target == null`. API chi tiết có thể khác theo phiên bản; cần xác minh project đang dùng Spring Framework phù hợp (ví dụ Spring Framework 6.1+), không sao chép đoạn này sang Spring 5.x rồi kỳ vọng biên dịch.

Ý tưởng chính:

```text
Chưa có CustomerRequest instance
    |
    v
new DataBinder(null, "customerRequest")
    |
    v
binder.setTargetType(ResolvableType.forClass(CustomerRequest.class))
    |
    v
binder.construct(ValueResolver cung cấp tên -> giá trị)
    |
    +--> Xác định constructor/parameter names
    +--> Lấy dữ liệu theo parameter names
    +--> Chuyển giá trị sang kiểu parameter
    +--> Gọi constructor tạo object
    +--> Ghi lỗi binding nếu có
    |
    v
binder.getTarget() và binder.getBindingResult()
```

`setTargetType` chỉ định **kiểu mong muốn**, chứ không tự tạo object. Chính `construct(...)` mới bắt đầu quá trình tạo instance. Đây là điểm khác với `bind(...)`, vốn gắn property values vào object đã tồn tại.

## 2. Hai chế độ binding và vòng đời của target

| Khía cạnh | Property binding | Constructor binding |
| --- | --- | --- |
| Target ban đầu | Thường là object đã được tạo | Có thể là `null` |
| Cấu hình quan trọng | Property access, allowed fields, conversion | `targetType`, constructor metadata, value resolver, conversion |
| Lệnh thực hiện | `bind(PropertyValues)` | `construct(DataBinder.ValueResolver)` |
| Dữ liệu được gắn vào | Setter/field của instance hiện có | Tham số constructor tạo instance mới |
| Mô hình phù hợp | Mutable JavaBean/DTO | Immutable DTO, record, constructor-based DTO |
| Kết quả | Object bị cập nhật | Object mới có thể lấy qua `getTarget()` |
| Lỗi dữ liệu | `BindingResult` | `BindingResult`/lỗi constructor tùy loại vấn đề |

Trong một lần xử lý, Spring MVC có thể kết hợp constructor binding khi tạo model attribute và property binding sau đó theo đường thực thi và cấu hình. Vì vậy **không nên giả định** `construct` và `bind` loại trừ nhau trong mọi trường hợp. Đối với immutable DTO, property binding sau tạo object thường không có setter để thực hiện.

## 3. Vì sao target null cần targetType?

Khi gọi `new DataBinder(null, "customer")`, binder không thể suy ra class từ `target.getClass()` vì chưa có target. Nếu cần constructor binding, hãy cung cấp `ResolvableType` để Spring biết kiểu object cần tạo:

```java
import org.springframework.core.ResolvableType;
import org.springframework.validation.DataBinder;

DataBinder binder = new DataBinder(null, "customer");
binder.setTargetType(ResolvableType.forClass(CustomerRequest.class));
```

Đây là snippet nằm trong phương thức có class `CustomerRequest` đã định nghĩa. `ResolvableType` có thể biểu diễn thông tin type phức tạp hơn một raw `Class`, ví dụ generic type metadata khi cần. Khi target đã không null, không nên dùng `setTargetType` để “đổi kiểu” đối tượng sẵn có; nó phục vụ tình huống binder phải xác định target class cho bước construction.

Thiết lập target type **trước** `construct()`. Việc thiếu target type với target null khiến binder không đủ thông tin để chọn constructor thích hợp.

## 4. Định nghĩa target phù hợp cho constructor binding

Java record là lựa chọn đơn giản vì các thành phần dữ liệu tương ứng với canonical constructor:

```java
public record CustomerRequest(String name, int age) {}
```

Đối với class thường, cần đảm bảo Spring tìm được constructor phù hợp và tên tham số có thể được phát hiện. Biên dịch Java với option `-parameters` khi cần hỗ trợ metadata tên tham số runtime (và cấu hình build tương ứng). Ví dụ:

```java
public final class CustomerRequest {
    private final String name;
    private final int age;

    public CustomerRequest(String name, int age) {
        this.name = name;
        this.age = age;
    }

    public String getName() { return name; }
    public int getAge() { return age; }
}
```

Nếu các tên parameter ở runtime trở thành `arg0`, `arg1` do thiếu metadata, binder có thể không ghép được các input `name`, `age` như mong đợi. Với record, canonical constructor và record components cung cấp thông tin tên ổn định hơn theo hỗ trợ của framework.

## 5. Ví dụ Java 17+ đầy đủ sử dụng `DataBinder.construct`

Tạo file `ConstructorBindingDemo.java` trong dự án có Spring Framework **6.1+** và các dependency tương thích:

```java
import java.util.Map;
import org.springframework.core.ResolvableType;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public class ConstructorBindingDemo {
    public record CustomerRequest(String name, int age) {}

    public static void main(String[] args) {
        Map<String, String> input = Map.of(
                "name", "An",
                "age", "21");

        DataBinder binder = new DataBinder(null, "customerRequest");
        binder.setTargetType(
                ResolvableType.forClass(CustomerRequest.class));

        binder.construct(new DataBinder.ValueResolver() {
            @Override
            public Object resolveValue(String name, Class<?> type) {
                return input.get(name);
            }
        });

        CustomerRequest target = (CustomerRequest) binder.getTarget();
        BindingResult result = binder.getBindingResult();

        System.out.println(target.name());
        System.out.println(target.age());
        System.out.println(result.hasErrors());
    }
}
```

Kết quả mong đợi (Spring Framework phù hợp, classpath đầy đủ):

```text
An
21
false
```

Giải thích luồng:

1. Binder bắt đầu với target `null`.
2. `setTargetType` truyền `CustomerRequest.class` vào binder.
3. `ValueResolver` nhận tên và kiểu tham số; ví dụ trả chuỗi đầu vào theo `name` hoặc `age`.
4. `construct` tìm canonical constructor của record, dùng conversion của Spring để chuyển `"21"` sang `int` và gọi constructor.
5. Sau construction, `getTarget()` trả `CustomerRequest`; `getBindingResult()` cho biết lỗi binding nếu có.

**Lưu ý compatibility:** tùy minor version, `DataBinder.ValueResolver` có thêm hợp đồng hỗ trợ tên, như `getNames()`, được cung cấp dưới dạng phương thức mặc định. Khi dùng `new DataBinder.ValueResolver()`, cần đối chiếu interface thực tế của dependency. Nếu compiler báo thiếu phương thức abstract, phải triển khai đúng contract phiên bản đang dùng; không suy luận API từ một phiên bản khác.

Với dependencies đã được build tool phân giải trong biến `SPRING_CP`, có thể biên dịch/chạy trên Linux/macOS:

```bash
javac -cp "$SPRING_CP" ConstructorBindingDemo.java
java -cp ".:$SPRING_CP" ConstructorBindingDemo
```

Trên Windows, dùng dấu `;` để phân tách classpath. Đoạn code không biên dịch bằng JDK thuần nếu không có Spring JAR. Ứng dụng Spring Boot thường quản lý phiên bản Spring Framework qua BOM/starter; không trộn các phiên bản Spring riêng lẻ.

## 6. Truyền dữ liệu qua `DataBinder.ValueResolver`

`ValueResolver` là ranh giới giữa **nguồn dữ liệu** và **cơ chế tạo object**. Thay vì yêu cầu nguồn dữ liệu có một định dạng duy nhất, binder hỏi resolver về giá trị của từng constructor parameter:

```java
Object resolveValue(String name, Class<?> type)
```

Ví dụ khi đang tạo `CustomerRequest(String name, int age)`:

```text
resolveValue("name", String.class) -> "An"
resolveValue("age", int.class)     -> "21"
```

Không bắt buộc resolver phải trả ngay giá trị cùng kiểu Java với tham số; Spring có thể thực hiện conversion sau đó. Tuy nhiên giá trị được trả phải có khả năng chuyển đổi thích hợp, và converter cần được đăng ký nếu target type là kiểu domain tùy biến.

Resolver thường nhận dữ liệu qua map, request parameters hay nguồn nhập khác. Trong Spring MVC, framework có binder chuyên cho web, và factory/resolver tương ứng chuẩn bị dữ liệu request. Khi tự viết resolver, bạn chịu trách nhiệm về việc tìm khóa, multiple values, missing values và boundary dữ liệu không tin cậy.

### Vấn đề tên parameter

Không phải tất cả constructor đều an toàn để bind tự động. Nếu constructor tham số có tên khó xác định hoặc nhiều overload gây mơ hồ, cần cấu hình/model rõ và kiểm thử. Khi muốn tên input khác tên parameter, Spring có các cơ chế đặt tên trong trường hợp được hỗ trợ (ví dụ annotation liên quan constructor binding); phải dùng đúng API/phiên bản thay vì đoán.

## 7. Lỗi conversion và dữ liệu thiếu

Giả sử input chứa:

```text
name=An
age=abc
```

`age` của record là `int`. Spring không thể chuyển `"abc"` thành số nguyên, nên bước tạo object không thành công theo cách bình thường. Binder có thể ghi `FieldError` với mã `typeMismatch`, nhưng **không nên giả định** một record hợp lệ sẽ luôn được tạo khi constructor argument không convert được: target có thể vẫn null hoặc quá trình có thể kết thúc bằng exception tùy kiểu lỗi và phiên bản.

Đối với input thiếu tên hoặc giá trị:

- Constructor có parameter primitive như `int` không nhận `null` như reference type.
- Một `Integer` nullable có thể cho phép `null` ở mức Java constructor, nhưng nghiệp vụ vẫn cần validate yêu cầu bắt buộc.
- Nếu constructor tự ném `IllegalArgumentException`, đây là lỗi từ logic constructor, không mặc nhiên tương đương `FieldError` của conversion.
- Không nên gọi `binder.getTarget()` rồi ép kiểu hoặc dùng ngay khi dữ liệu đầu vào không hợp lệ; kiểm tra lỗi và trạng thái target an toàn trước.

Các ràng buộc như tuổi phải từ 18 trở lên là **validation sau khi có dữ liệu có thể kiểm tra**, không đồng nghĩa với trách nhiệm chọn constructor và chuyển kiểu. Nếu muốn kiểm tra các constraints qua Jakarta Bean Validation hoặc Spring Validator, cần cấu hình/kích hoạt đúng luồng.

## 8. Constructor binding trong Spring MVC

Khi Spring MVC xử lý một `@ModelAttribute`, framework có thể dùng constructor binding để tạo object từ request values trước khi tiếp tục các bước cần thiết.

```java
import org.springframework.validation.BindingResult;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CustomerController {
    public record CustomerRequest(String name, int age) {}

    @PostMapping("/customers")
    public String create(
            @Validated @ModelAttribute CustomerRequest form,
            BindingResult result) {
        if (result.hasErrors()) {
            return "Invalid customer";
        }
        return form.name() + ": " + form.age();
    }
}
```

Đây là **controller snippet**, không phải ứng dụng Spring MVC có `main` hoàn chỉnh. Khi request gửi `name=An&age=21` và cấu hình MVC hỗ trợ constructor binding phù hợp, object record có thể được tạo với giá trị đã chuyển kiểu. `BindingResult` phải đứng liền sau tham số model. `@Validated` yêu cầu validation qua validator đang cấu hình; nếu không có constraint, nó không tự đặt yêu cầu `age >= 18`.

### Phân biệt `@ModelAttribute` với `@RequestBody`

`@ModelAttribute` thường gắn request parameters vào object và có thể tham gia constructor/property binding. `@RequestBody` JSON thường do `HttpMessageConverter` (ví dụ Jackson) deserialize; dù Jackson cũng có thể dùng constructor/record, đó là **một cơ chế tạo object khác**. Không nên đồng nhất mọi deserialization của JSON với `DataBinder.construct(ValueResolver)`.

### Phạm vi và bảo mật

Constructor binding giới hạn dữ liệu được truyền vào constructor parameters của DTO (thường hữu ích cho immutable request objects), nhưng **không có nghĩa tự miễn nhiễm mass assignment**. Nếu model có constructor parameter nhạy cảm như `admin`, client có thể tìm cách cung cấp tên đó. Chỉ đưa những trường được phép nhận từ client vào DTO constructor; kiểm tra authorization riêng và tránh bind trực tiếp security/domain entity.

## 9. `targetType`, `ConversionService` và `BindingResult` phối hợp ra sao?

| Thành phần | Vai trò trong constructor binding |
| --- | --- |
| `ResolvableType targetType` | Xác định kiểu object Spring cần tạo khi chưa có target |
| `ValueResolver` | Lấy giá trị đầu vào theo tên và kiểu constructor parameter |
| `ConversionService` | Chuyển giá trị nguồn sang kiểu constructor parameter |
| `DataBinder.construct(...)` | Chọn/gọi constructor và tạo object |
| `DataBinder.getTarget()` | Lấy object sau khi tạo thành công |
| `BindingResult` | Truy vấn lỗi binding; không phải bản sao object |

Khi dùng kiểu dữ liệu riêng như `Money`, `ProductCode`, hoặc enum với format bất thường, bạn có thể cấu hình conversion service cho binder trước `construct`. Converter chỉ có nhiệm vụ chuyển kiểu, không thay thế validation nghiệp vụ.

Ví dụ cấu hình conversion (snippet trong method):

```java
import org.springframework.core.convert.support.DefaultConversionService;

var conversionService = new DefaultConversionService();
binder.setConversionService(conversionService);
binder.construct(valueResolver);
```

`binder` và `valueResolver` ở đoạn này phải được tạo trước; đây là **snippet minh họa**, không phải tệp độc lập. Với các kiểu thông dụng như `String` sang số nguyên, hạ tầng binder thường có đường chuyển đổi mặc định phù hợp.

## 10. Những lỗi triển khai thường gặp

- **Quên `setTargetType` với binder target null:** Spring không biết constructor của kiểu nào cần dùng.
- **Gọi `bind(PropertyValues)` trước khi tạo target:** property binding không thể gán lên object chưa tồn tại; cần cơ chế constructor binding khi bắt đầu từ null.
- **Cho rằng `setTargetType` tự khởi tạo object:** nó chỉ lưu metadata kiểu.
- **Không có tên constructor parameter:** resolver không ánh xạ được key input mong đợi; với class thường, kiểm tra `-parameters`.
- **Model immutable nhưng trông chờ setter:** record không có setters để property binder cập nhật sau construction.
- **Trộn API giữa Spring 5/6 hoặc minor versions:** hãy kiểm tra `DataBinder.construct` và `ValueResolver` trong dependency thật.
- **Cho rằng mọi conversion failure sẽ có target hợp lệ:** cần đọc `BindingResult` và xử lý khi target không được tạo.
- **Dùng `@Validated` và tưởng tự sinh constraint:** cần quy tắc validation thực tế.
- **Bind trực tiếp đối tượng chứa tham số nhạy cảm:** constructor binding vẫn cần DTO, input constraints và authorization.

## 11. Checklist trước khi sử dụng

1. Phiên bản Spring đang dùng có hỗ trợ constructor binding APIs dự định gọi?
2. Đối tượng đích có constructor/record component names rõ ràng và phù hợp các input names?
3. Binder được tạo với target null và đã gọi `setTargetType` trước `construct`?
4. `ValueResolver` trả giá trị chính xác, xử lý trường thiếu/multiple values hợp lý?
5. Conversion service chuyển được toàn bộ tham số cần thiết?
6. Khi lỗi, ứng dụng kiểm tra `BindingResult` và target trước khi sử dụng?
7. Validation, ranh giới dữ liệu và quyền thay đổi của client được thiết kế riêng?

**Kết luận:** Để gắn dữ liệu bằng constructor khi chưa có object, tạo `DataBinder` với target null, khai báo `targetType` bằng `ResolvableType`, cung cấp `ValueResolver` rồi gọi `construct`. Khác với `bind` trên mutable JavaBean, luồng này tạo object trước khi có thể đọc qua `getTarget()`, phù hợp record và immutable DTO nhưng yêu cầu quản lý tên tham số, chuyển kiểu, lỗi và bảo mật cẩn thận.