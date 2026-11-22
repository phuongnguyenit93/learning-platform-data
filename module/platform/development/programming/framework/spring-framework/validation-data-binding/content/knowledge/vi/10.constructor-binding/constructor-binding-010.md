# BindingResult khi chuyển đổi hoặc khởi tạo gặp lỗi

## 1. Bức tranh tổng quan

**Constructor binding** trong Spring Framework tạo đối tượng mới bằng cách lấy dữ liệu đầu vào, tìm tham số constructor, chuyển đổi kiểu từng giá trị rồi gọi constructor. Spring `DataBinder` cung cấp API `construct(DataBinder.ValueResolver)` cho quy trình này (Spring Framework 6.1+).

Điểm cần nắm: **lỗi chuyển đổi tham số** và **lỗi thực thi constructor** không nhất thiết đi qua cùng một nhánh xử lý.

- Khi một tham số như `age` cần `Integer` nhưng đầu vào là `"abc"`, cơ chế chuyển kiểu có thể tạo lỗi `typeMismatch`, được ghi trong `BindingResult` dưới dạng `FieldError`.
- Khi tất cả tham số chuyển kiểu được nhưng chính constructor ném `IllegalArgumentException` vì một bất biến, Spring có thể ném `BeanInstantiationException`. Đừng tự giả định ngoại lệ này luôn được chuyển thành `FieldError`.
- Khi thiếu một tham số, giá trị có thể được xem là `null` hoặc xử lý theo chính sách của kiểu tham số/constructor; **không mặc nhiên** sinh lỗi `required` của property binding.
- Khi có lỗi trong `BindingResult`, object đích **có thể** đã được tạo thành công hoặc **không** được tạo. Phải kiểm `hasErrors()`, không coi `getTarget() != null` là chứng chỉ dữ liệu hợp lệ.
- Khi chạy ở Spring MVC, lỗi có thể được đưa tới tham số `BindingResult` ngay sau `@ModelAttribute`, hoặc framework đưa lỗi tới exception handler. Không nên đồng nhất mọi trường hợp này với ngoại lệ của Jackson khi parse `@RequestBody`.

Bài này tập trung vào **ngữ cảnh “Gắn qua constructor”**, nghĩa là khởi tạo đối tượng từ dữ liệu chưa tin cậy trước khi sử dụng cho nghiệp vụ; không nhầm nó với Java constructor injection của dependency vào Spring Bean.

### Mục tiêu

Sau khi học, bạn có thể tạo `DataBinder` với target ban đầu là null; tự viết `ValueResolver`; phân tích `BindingResult` khi chuyển kiểu lỗi; phân biệt constructor ném exception; xử lý những tình huống có/không có target, field error, rejected value, object error; và thiết kế kiểm thử phù hợp cho controller/CLI.

## 2. Luồng xử lý và thời điểm hình thành lỗi

Đường đi khái quát:

~~~text
Input (query/form/map)
    |
    v
DataBinder(null, "input")
    |  setTargetType(ResolvableType.forClass(Input.class))
    v
construct(ValueResolver)
    |
    +--> tìm constructor và tên tham số
    |
    +--> tra từng giá trị theo tên/đường dẫn lồng nhau
    |
    +--> convertIfNecessary(value, parameterType)
    |       |
    |       +--> thành công -> lưu giá trị đã chuyển đổi
    |       |
    |       +--> TypeMismatchException
    |               |
    |               +--> BindingResult / FieldError ("typeMismatch")
    |
    +--> thử tạo target từ các đối số (tùy lỗi đã ghi và loại constructor)
            |
            +--> tạo thành công -> có thể có target
            |
            +--> constructor thất bại -> có thể không có target
                         |
                         +--> BeanInstantiationException được ném ở một số tình huống
                         +--> lỗi có thể được ghi vào BindingResult ở tình huống
                              đặc thù (ví dụ xử lý Kotlin nullability)

Sau construct:
    +--> kiểm getBindingResult().hasErrors() và chi tiết lỗi
    +--> chỉ dùng target cho nghiệp vụ khi không có lỗi và target hợp lệ
~~~

Điểm mấu chốt trong Java API:

~~~java
DataBinder binder = new DataBinder(null, "input");
binder.setTargetType(ResolvableType.forClass(Input.class));
binder.construct(valueResolver);

BindingResult result = binder.getBindingResult();
if (result.hasErrors()) {
    // Đọc FieldError/ObjectError, chưa dùng object cho nghiệp vụ.
}
~~~

Đây là **mảnh code** thuộc ứng dụng đã có class `Input`, `valueResolver`, dependency Spring và các import `DataBinder`, `ResolvableType`, `BindingResult`; chương trình chạy độc lập đầy đủ sẽ nằm ở phần 6.

**Ba điều kiện trước `construct(...)`:** binder chưa có target, kiểu target đã được khai báo bằng `setTargetType(...)` và `ValueResolver` biết cách trả giá trị theo tên tham số. Nếu không thiết lập các điều kiện này, một lỗi cấu hình/lập trình có thể phát sinh trước khi có kết quả binding hữu ích.

## 3. Cách Spring tìm constructor và tham số

Spring ưu tiên constructor phù hợp để tạo dữ liệu:

1. Với kiểu có một data constructor thích hợp, Spring lấy các tham số và tìm giá trị đầu vào có tên tương ứng.
2. Với kiểu có default/no-arg constructor phù hợp, framework có thể dùng đường tạo JavaBean mặc định; các property sau đó phải được bind riêng bằng setter nếu caller cho phép.
3. Với record Java, canonical constructor và tên component tạo một mô hình tự nhiên cho constructor binding.
4. Với class bình thường, nên bảo đảm **tên tham số constructor có trong metadata** (ví dụ biên dịch với `-parameters` hoặc dùng `@ConstructorProperties` khi phù hợp) và không thiết kế nhiều constructor mơ hồ.
5. Spring MVC/WebFlux hỗ trợ `@BindParam` để ánh xạ tên request khác tên constructor parameter, trong khi một `DataBinder` dùng độc lập có thể cấu hình `DataBinder.NameResolver`.

Ví dụ mã đặt trong class nhận dữ liệu:

~~~java
public record CreatePerson(String name, Integer age) {}
~~~

Khi gặp `name=Lan&age=20`, Spring có thể tìm `name` và `age`, chuyển chuỗi `"20"` thành `Integer 20` rồi gọi canonical constructor.

Nếu client gửi `personAge=20` thay vì `age=20`, không thể tự kỳ vọng Spring đoán tên trường. Đặc biệt khi dữ liệu có đường dẫn lồng như `address.city`, resolver phải biết những tên đó; các giá trị con có thể được dùng để dựng object lồng theo constructor. Với collection/list/map, Spring 6.2 hỗ trợ cả dạng chuỗi có thể chuyển đổi và indexed keys trong constructor binding.

**Đừng nhầm thiếu tên với sai kiểu:** `age` không hiện diện có thể cho `null` đối với `Integer`; còn `age="abc"` là một giá trị có mặt nhưng không chuyển được sang `Integer`. Đó là hai bài toán và mã lỗi khác nhau.

## 4. BindingResult lưu gì khi chuyển đổi thất bại?

`BindingResult` mở rộng `Errors`, là nơi tập hợp thông tin lỗi ở cấp field và object trong Spring:

| API | Ý nghĩa |
| --- | --- |
| `binder.getBindingResult()` | Truy cập kết quả gắn với binder |
| `result.hasErrors()` | Có một hoặc nhiều lỗi đã đăng ký |
| `result.getErrorCount()` | Tổng số `FieldError` và `ObjectError` |
| `result.hasFieldErrors("age")` | Field cụ thể có lỗi không |
| `result.getFieldError("age")` | Lỗi đầu tiên của field `age`, hoặc null |
| `result.getFieldErrors()` | Danh sách lỗi ở mức field |
| `result.getGlobalErrors()` | Lỗi cấp object (không gắn một field cụ thể) |
| `fieldError.getField()` | Tên field gây lỗi, có thể là `address.zip` |
| `fieldError.getCode()` | Mã lỗi chính; thường là `typeMismatch` khi convert thất bại |
| `fieldError.getRejectedValue()` | Giá trị đầu vào bị từ chối, giúp hiển thị lại có chọn lọc |
| `fieldError.isBindingFailure()` | Cho biết lỗi thuộc quá trình binding/chuyển kiểu, thay vì constraint validation thông thường |
| `result.getObjectName()` | Tên object được bind, ví dụ `input` |
| `result.getTarget()` | Target đang được kết quả cụ thể bọc; có thể là null |
| `binder.getTarget()` | Target gắn với binder sau khi thử `construct`; có thể là null |

Một `FieldError` là `ObjectError` có thêm thông tin field. Code `typeMismatch` thường được `DefaultMessageCodesResolver` mở rộng thành nhiều mã cụ thể hơn để tra cứu thông điệp với `MessageSource`. Không nên dựa vào nguyên văn `getDefaultMessage()` hoặc `toString()` để xác định loại lỗi, vì thông điệp có thể chịu ảnh hưởng locale, resolver và cấu hình formatter/converter.

Ví dụ đọc lỗi an toàn:

~~~java
BindingResult result = binder.getBindingResult();

for (FieldError error : result.getFieldErrors()) {
    String field = error.getField();
    String code = error.getCode();
    boolean conversionOrBinding = error.isBindingFailure();
    Object rejected = error.getRejectedValue();

    // Lập phản hồi có cấu trúc theo field/code;
    // tránh log hoặc trả nguyên văn dữ liệu nhạy cảm.
}
~~~

Đây là **mảnh code** cần import `BindingResult`/`FieldError`. Với input có password/token, `rejected` có thể chứa bí mật. Chỉ hiển thị giá trị bị từ chối nếu hợp đồng và chính sách bảo mật thực sự cho phép.

### Một điểm ít được chú ý: khi chưa có target

Constructor binding khác property binding thông thường ở chỗ **target lúc bắt đầu là null**. Nếu việc tạo target không hoàn thành, Spring vẫn có thể giữ giá trị của các constructor argument để phản hồi lỗi. `BindingResult.recordFieldValue(...)` được thiết kế để lưu giá trị field khi không dựng được object; `getFieldValue(...)` có thể dùng giá trị được ghi nhận hoặc rejected value tương ứng. Tuy nhiên không coi `getFieldValue(...)` là bản sao lossless của toàn bộ request; nếu cần raw request để audit hay retry, phải lưu thông tin hợp lệ ở boundary với biện pháp bảo mật riêng.

**Quan trọng:** `binder.getTarget()` và `result.getTarget()` không nên bị giả định luôn đồng nhất ở mọi thời điểm trong quá trình constructor binding có lỗi; BindingResult có thể được tạo trước khi target hoàn thành. Hãy hỏi `result.hasErrors()` trước, rồi mới quyết định có được dùng target hay không.

## 5. Phân biệt các nhóm thất bại

| Tình huống | Ví dụ | Cơ chế thường gặp | Dấu hiệu |
| --- | --- | --- | --- |
| Chuyển kiểu lỗi | `age="xyz"` với `Integer age` | `TypeMismatchException` trong conversion được binder ghi nhận | `FieldError`, mã `typeMismatch`, `isBindingFailure=true` |
| Converter có logic không hợp lệ | Chuỗi ngày sai định dạng | Converter/formatter không chuyển được | Lỗi field từ conversion nếu Spring bắt và chuyển lỗi |
| Thiếu tham số nullable | Không gửi `age` cho `Integer age` | Có thể dùng null; tự nó chưa nhất thiết là lỗi | Phụ thuộc constructor/validation |
| Thiếu tham số primitive | Không gửi `age` cho `int age` | Cần xem conversion mặc định và xử lý argument | Không suy luận mặc định thành `required` của property binding |
| Constructor tự ném exception | Constructor kiểm `name.isBlank()` rồi ném | Có thể bọc/ném `BeanInstantiationException` | Exception thay vì `FieldError` thường quy |
| Constructor không hợp lệ về cấu hình | Không có constructor phù hợp, thiếu metadata tên tham số | Lỗi cấu hình hoặc object creation | Exception cần xử lý riêng |
| Ràng buộc Bean Validation | `@NotBlank`, `@Min` trên DTO | Cần validation thực sự được kích hoạt | `FieldError`/`ObjectError` có mã constraint |
| Bất biến cross-field | `startDate > endDate` | Custom validator hoặc constructor guard | Lỗi object/field **hoặc** exception tùy nơi kiểm |
| Nested constructor binding | `address.zip="oops"` | Convert tham số của object lồng thất bại | Field path lồng như `address.zip` nếu được ghi nhận |

**Không đồng nhất các lỗi:**

- `TypeMismatchException` là lỗi tầng chuyển kiểu.
- `FieldError` là **dữ liệu mô tả lỗi** đã ghi vào `BindingResult`.
- `BeanInstantiationException` là **exception khởi tạo object**, không phải mặc định một `FieldError`.
- `BindException` có thể được ném khi code chủ động dùng `DataBinder.close()` mà `BindingResult` có lỗi; `close()` không tự tạo lỗi conversion hay gọi validation.
- `MethodArgumentNotValidException` là một dạng lỗi thường thấy tại Spring MVC khi handler argument không thể được bind/validate hợp lệ và không được controller xử lý bằng `BindingResult` phù hợp.

### Tại sao lỗi constructor không luôn là typeMismatch?

Giả sử `new Invoice("INV-1", -10)` gọi constructor có:

~~~java
public Invoice(String id, int amount) {
    if (amount < 0) {
        throw new IllegalArgumentException("negative amount");
    }
    this.id = id;
    this.amount = amount;
}
~~~

Đây là **mảnh class/method** chứ không phải chương trình hoàn chỉnh. Giá trị `"-10"` có thể chuyển thành `int -10` rất tốt. Exception phát sinh từ **logic trong constructor**, không phải conversion. Nếu cần mã lỗi ổn định cho request, nên thiết kế ràng buộc ở tầng validation/adapter phù hợp thay vì dựa vào parsing thông điệp `BeanInstantiationException`.

## 6. Ví dụ Java 17 chạy độc lập (Spring Framework 6.2)

Ví dụ này sử dụng API `DataBinder.construct()` thực sự, một `ValueResolver` đọc từ `Map` và một record Java làm đích. Chúng ta kiểm chứng ba nhánh:

1. Chuyển đổi thành công, không có lỗi.
2. Dữ liệu sai kiểu, xuất hiện `FieldError` trong `BindingResult`.
3. Constructor guard ném lỗi dù conversion không sai kiểu.

Thêm một ca thiếu field để thấy missing nullable **không tự động trở thành typeMismatch**.

Không cần Spring Boot hoặc server HTTP. Cần **JDK 17+ và Maven**. Tạo một thư mục mới cho ví dụ và thêm tệp `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>constructor-binding-errors-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
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

Tạo tệp `src/main/java/ConstructorBindingErrorsDemo.java`:

~~~java
import java.util.Map;
import java.util.Set;

import org.springframework.beans.BeanInstantiationException;
import org.springframework.core.ResolvableType;
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

public class ConstructorBindingErrorsDemo {

    public record Input(String name, Integer age) {}

    public record StrictInput(String name, Integer age) {
        public StrictInput {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name is required");
            }
        }
    }

    public static final class MapResolver
            implements DataBinder.ValueResolver {

        private final Map<String, String> input;

        public MapResolver(Map<String, String> input) {
            this.input = input;
        }

        @Override
        public Object resolveValue(String name, Class<?> targetType) {
            return input.get(name);
        }

        @Override
        public Set<String> getNames() {
            return input.keySet();
        }
    }

    private static DataBinder construct(
            Class<?> type, Map<String, String> values) {

        DataBinder binder = new DataBinder(null, "input");
        binder.setTargetType(ResolvableType.forClass(type));
        binder.setConversionService(new DefaultConversionService());
        binder.construct(new MapResolver(values));
        return binder;
    }

    public static void main(String[] args) {
        DataBinder valid = construct(
            Input.class, Map.of("name", "Lan", "age", "20"));

        System.out.println(
            "valid: errors=" + valid.getBindingResult().hasErrors());
        System.out.println(
            "valid: age=" + ((Input) valid.getTarget()).age());

        DataBinder bad = construct(
            Input.class, Map.of("name", "Lan", "age", "abc"));

        BindingResult result = bad.getBindingResult();
        FieldError ageError = result.getFieldError("age");

        System.out.println(
            "badAge: errors=" + result.hasErrors());
        System.out.println(
            "badAge: fieldError=" + (ageError != null));
        System.out.println(
            "badAge: typeMismatch=" +
            (ageError != null &&
                "typeMismatch".equals(ageError.getCode())));
        System.out.println(
            "badAge: rejected=" +
            (ageError != null ? ageError.getRejectedValue() : "<none>"));

        DataBinder missing = construct(
            Input.class, Map.of("name", "Lan"));

        System.out.println(
            "missing: errors=" + missing.getBindingResult().hasErrors());
        System.out.println(
            "missing: ageNull=" +
            (((Input) missing.getTarget()).age() == null));

        try {
            construct(
                StrictInput.class, Map.of("name", "", "age", "20"));
            System.out.println("guard: constructorFailure=false");
        } catch (BeanInstantiationException ex) {
            System.out.println("guard: constructorFailure=true");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=ConstructorBindingErrorsDemo
~~~

**Stdout của chương trình**, không tính thông báo môi trường Maven:

~~~text
valid: errors=false
valid: age=20
badAge: errors=true
badAge: fieldError=true
badAge: typeMismatch=true
badAge: rejected=abc
missing: errors=false
missing: ageNull=true
guard: constructorFailure=true
~~~

### Phân tích kết quả

**Ca valid:** `age="20"` được đổi thành `Integer 20` bởi conversion service. Record `Input("Lan", 20)` được khởi tạo; `BindingResult.hasErrors()` là false và caller có thể dùng target sau khi kiểm các ràng buộc khác của ứng dụng.

**Ca badAge:** chuỗi `"abc"` không thể thành `Integer`, vì thế `DataBinder.construct()` ghi lỗi field `age` với mã `typeMismatch`, giữ rejected value giúp phản hồi cho người dùng. Khi có `FieldError`, code không lấy một đối tượng có thể tồn tại để thực hiện nghiệp vụ. Đừng dựa trên sự hiện diện của target để thay cho kiểm `hasErrors()`.

**Ca missing:** vì `age` là `Integer` (nullable) và record không có guard/constraint đối với null, thiếu field tự nó không tạo type mismatch trong ví dụ. Nếu quy tắc yêu cầu tuổi bắt buộc, cần khai báo/kiểm validation thích hợp.

**Ca guard:** giá trị `age="20"` được chuyển kiểu thành công, còn `name=""` là String hợp lệ theo bộ chuyển kiểu. Chính compact constructor của `StrictInput` ném `IllegalArgumentException`, được Spring phản ánh bằng `BeanInstantiationException` trong nhánh này. Chương trình bắt ngoại lệ riêng thay vì giả định một `FieldError` đã được sinh.

**Giới hạn ví dụ:** source code này được thiết kế và kiểm tra tĩnh dựa trên hợp đồng Spring 6.2; nếu chạy trên ứng dụng có custom converter, custom `BindingErrorProcessor`, Kotlin constructor hoặc các cấu hình ngoài mặc định, nội dung lỗi và đường xử lý có thể khác. Đừng sao chép nguyên văn expected stdout làm hợp đồng API đa phiên bản mà không chạy test trên dependency thực tế.

## 7. Nếu constructor nhận int thay cho Integer thì sao?

Ví dụ dùng `Integer` ở trên có chủ đích. `Integer` cho phép `null`, trong khi `int` là primitive, không thể nhận Java null theo cách tương tự. Nếu thiếu `age` hoặc conversion cho `int` thất bại, framework có thể ghi nhận lỗi hoặc gặp vấn đề khi dựng đối số, tùy quy trình và phiên bản.

Do đó:

- Đối với trường đầu vào **có thể thiếu**, hãy biểu diễn trạng thái đó bằng wrapper/nullability phù hợp và xử lý ở validation.
- Đối với trường **bắt buộc**, đừng chỉ phụ thuộc vào kiểu `int` để thông báo “required”; hãy kiểm yêu cầu dữ liệu vào bằng constraint và lỗi có cấu trúc.
- Nếu cần phân biệt **không gửi field** với **gửi null**, một `Integer` đơn lẻ sau binding có thể không lưu đủ thông tin presence. Đọc dữ liệu đầu vào ở boundary khi contract cần phân biệt hai trường hợp.
- Không cố “sửa” lỗi primitive bằng cách tự điền `0` nếu `0` cũng có ý nghĩa nghiệp vụ. Phân biệt defaulting với validation.

### Không nhầm required của property binding

`binder.setRequiredFields("age")` áp dụng cho đường **`bind(PropertyValues)`** (property binding), không phải một cách tổng quát để làm tất cả constructor parameter bắt buộc trong `construct(ValueResolver)`. Constructor binding dùng những tham số mà constructor khai báo, còn việc bắt buộc có mặt/khác null/hợp lệ cần được thiết kế riêng bằng contract và validation.

Nếu người học gọi:

~~~java
binder.setRequiredFields("age");
binder.construct(valueResolver);
~~~

thì không nên mặc định rằng một `FieldError` với code `required` sẽ xuất hiện giống như `binder.bind(new MutablePropertyValues(...))`. Hai API có điểm mở rộng và cách kiểm field khác nhau.

## 8. Khi target null nhưng BindingResult vẫn hữu ích

Một bẫy phổ biến là: “`getTarget() == null` thì không có cách biết người dùng đã nhập gì”. Spring cung cấp cơ chế lưu lỗi ngay cả khi quá trình tạo object không hoàn tất.

Các khả năng cần phân biệt:

1. **Binder chưa gọi `construct()`:** target null đơn giản vì chưa khởi tạo; không đồng nghĩa có lỗi.
2. **Constructor binding có lỗi conversion:** `BindingResult` có thể có `FieldError` dù chưa có object hoàn chỉnh.
3. **Constructor chấp nhận các đối số dự phòng sau lỗi:** target có thể vẫn được tạo, nhưng `BindingResult` còn lỗi; không được coi object ấy là hợp lệ.
4. **Constructor ném exception mà Spring không chuyển thành error:** `construct()` có thể thoát bằng exception; caller phải xử lý ngoại lệ đó, không trông đợi luôn có một error list.
5. **Validation sau khi có target:** đây là giai đoạn khác; khi `@Valid` hoặc `binder.validate()` được kích hoạt, các constraint mới góp phần tạo lỗi validation.

Đối với conversion error, `FieldError.getRejectedValue()` là nguồn hữu ích hơn so với cố đọc getter trên một object chưa dựng thành công. `BindingResult.recordFieldValue(...)` cho phép ghi các field conversion thành công để view/error reporting dùng, kể cả khi target null. Một số API như `getModel()` có thể chứa target null cùng kết quả binding; caller không nên coi model có key target là bằng chứng khởi tạo thành công.

Ví dụ lỗi:

~~~java
BindingResult errors = binder.getBindingResult();

if (errors.hasErrors()) {
    for (FieldError field : errors.getFieldErrors()) {
        System.out.printf(
            "%s: %s (%s)%n",
            field.getField(),
            field.getCode(),
            field.isBindingFailure() ? "binding" : "validation"
        );
    }
    // Không gọi domain service với binder.getTarget().
}
~~~

Đây là **mảnh code**; cần import `BindingResult` và `FieldError`. Trong log production, tránh đưa rejected value của field chứa bí mật ra stdout hoặc response.

## 9. Validation của constructor argument khác lỗi khởi tạo

Không phải mọi kiểm tra tính hợp lệ đều xảy ra ở cùng bước:

| Loại kiểm tra | Khi nào? | Kết quả thường gặp |
| --- | --- | --- |
| Chuyển `String` thành `Integer`/date/enum | Trong lúc resolve constructor arguments | Lỗi type mismatch được ghi nếu có cơ chế xử lý binding tương ứng |
| Guard trong constructor | Khi constructor chạy | Có thể ném `BeanInstantiationException` qua reflection |
| Constraint trên record/component/field | Khi Bean Validation provider thực sự được kích hoạt | Constraint violation được chuyển sang lỗi validation theo ngữ cảnh |
| Custom Spring `Validator` | Khi gọi `binder.validate()` hoặc framework kích hoạt | `FieldError` / `ObjectError` trong `BindingResult` |
| Business invariant cần DB | Trong service/domain sau khi input hợp lệ | Domain error/exception giao dịch theo kiến trúc |

Ví dụ DTO dùng Jakarta Bean Validation, chỉ là **mảnh khai báo**:

~~~java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreatePersonRequest(
    @NotBlank String name,
    @NotNull @Min(18) Integer age
) {}
~~~

Annotation không tự chạy khi bạn gọi `new CreatePersonRequest(null, null)`; cần provider và điểm kích hoạt (ví dụ `@Valid` trên tham số controller hoặc `Validator.validate(...)` do caller gọi). Khi constructor binding đã có lỗi, cách Spring đánh giá constructor arguments và các constraint có thể phụ thuộc thiết lập validation cũng như phiên bản. Không khẳng định toàn bộ constraint validation luôn chạy sau mỗi thất bại conversion.

Nếu chính constructor chứa guard ném exception, `BeanInstantiationException` cũng không phải một lỗi `@NotBlank` được tự động format thành mã `NotBlank`. Muốn trả lỗi field ổn định cho khách hàng, nên thiết kế validation và exception mapping rõ ràng.

## 10. Spring MVC: BindingResult ngay sau @ModelAttribute

Trong annotated Spring MVC controller, một request form/query có thể được bind vào DTO qua constructor. Với lỗi binding/validation mà framework chuyển thành `BindingResult`, handler có thể kiểm lỗi cục bộ nếu khai báo đúng vị trí:

~~~java
@PostMapping("/people")
ResponseEntity<?> create(
        @Valid @ModelAttribute("person") CreatePersonRequest request,
        BindingResult result) {

    if (result.hasErrors()) {
        return ResponseEntity.badRequest().body(
            result.getFieldErrors().stream()
                .map(e -> e.getField() + ": " + e.getCode())
                .toList()
        );
    }
    return ResponseEntity.ok("created");
}
~~~

Đây là **mảnh handler method**, không chạy độc lập; cần các import Spring Web MVC, `jakarta.validation.Valid` và class `CreatePersonRequest` ở phần trước. `BindingResult` phải đứng ngay sau argument tương ứng. Nếu object không thể khởi tạo do constructor ném một exception vượt ra ngoài đường tích lũy lỗi của framework, không thể đảm bảo handler vẫn chạy để kiểm `result`.

Khi không có `BindingResult` liền sau `@ModelAttribute` để xử lý, Spring MVC 6.2 thường báo lỗi bind/validate argument bằng `MethodArgumentNotValidException`. Khi method validation được kích hoạt do constraint trực tiếp trên tham số/method, có thể gặp `HandlerMethodValidationException`. Còn lỗi `@RequestBody` JSON thường đi qua HTTP message conversion/Jackson; JSON parse/type/constructor-deserialization error có thể là `HttpMessageNotReadableException` trước bước Jakarta validation. Các trường hợp này khác với việc bạn chủ động gọi `DataBinder.construct(...)` ở một ứng dụng độc lập.

### Hướng xử lý HTTP API

- Trả mã HTTP phù hợp (thường `400 Bad Request` cho dữ liệu đầu vào sai).
- Ánh xạ `FieldError` sang field path và mã lỗi có thể đọc được, ví dụ `age: typeMismatch`.
- Không trả nguyên stack trace hay exception message từ Java reflection cho client.
- Có `@ControllerAdvice`/`ResponseEntityExceptionHandler` cho các lỗi không được xử lý cục bộ.
- Không để sự kiện nghiệp vụ, ghi database hoặc cập nhật domain chạy khi `BindingResult.hasErrors()`.

Một class record immutable có constructor guard là cách thể hiện invariant mạnh, nhưng **nó không tự hứa mọi lỗi guard sẽ được trả về JSON field error**. Quyết định giữa exception domain và lỗi validation cho HTTP ở boundary.

## 11. Nested constructor, collection và thông tin đường dẫn lỗi

Constructor binding không chỉ xử lý field phẳng. Ví dụ:

~~~java
public record Address(String city, Integer zip) {}

public record Registration(
    String name,
    Address address
) {}
~~~

Nếu input dùng path `address.city=Hanoi` và `address.zip=oops`, Spring có thể tạo `Address` qua constructor lồng và ghi nhận lỗi conversion có path `address.zip`. Tuy nhiên cách tạo nested object phụ thuộc việc resolver báo cáo tên hiện diện và quy tắc Spring xác định có dữ liệu cho nhánh lồng.

Với `ValueResolver` tự viết, hai method cần nhất quán:

~~~java
public Object resolveValue(String name, Class<?> type) {
    return input.get(name);
}

public Set<String> getNames() {
    return input.keySet();
}
~~~

Đây là **mảnh implementation của `DataBinder.ValueResolver`**, với `input` là một `Map<String, ?>`. `getNames()` đặc biệt hữu ích để Spring biết những path lồng nào hiện diện; không được trả tập tên bịa hoặc không đồng nhất với `resolveValue`.

Spring 6.2 cũng hỗ trợ constructor parameters kiểu list, map và array, bao gồm indexed/map-key paths. Với dữ liệu không tin cậy, cần giới hạn kích thước, độ sâu và ý nghĩa của tên field để tránh request quá lớn. Một field error trên nested path phải được mã hóa/hiển thị an toàn, tránh thao tác trực tiếp với path do client gửi như một quyền truy cập object graph tùy ý.

## 12. Những lỗi thiết kế dễ gặp

1. **Lấy target trước khi kiểm lỗi.** Target có thể đã được tạo dù `BindingResult` có lỗi, hoặc vẫn null. Luôn xem `hasErrors()` trước khi sử dụng.
2. **Coi mọi lỗi là `FieldError`.** Constructor guard có thể ném `BeanInstantiationException` và không trở thành lỗi field theo ý muốn.
3. **Nghĩ `construct()` chính là `bind(PropertyValues)`.** Một API chọn constructor arguments; API kia gán property và có các rule `allowedFields/requiredFields`.
4. **Dùng `setRequiredFields(...)` để bảo đảm constructor parameter bắt buộc.** API này gắn với property binding; cần validation phù hợp cho constructor binding.
5. **Giả định missing luôn là `typeMismatch`.** Với `Integer` nullable có thể nhận null và không tạo lỗi trong cấu hình đơn giản.
6. **Dùng `int` hoặc default `0` để thay cho biểu diễn thiếu field.** Dễ che giấu input chưa có giá trị thật.
7. **Bỏ qua thông tin tên tham số constructor.** Không có metadata đúng hoặc `@BindParam` thích hợp, resolver không tìm được giá trị mong muốn.
8. **Bắt một `BindException` rồi nghĩ đã bao hết mọi lỗi khởi tạo.** `BeanInstantiationException` và lỗi cấu hình có đường đi khác.
9. **Đọc rejected value rồi log nguyên văn.** Dữ liệu có thể chứa password, token, mã truy cập hoặc thông tin nhạy cảm.
10. **Phụ thuộc thứ tự danh sách message codes hoặc nguyên văn exception string.** Cấu hình resolver, locale và version có thể thay đổi chi tiết.
11. **Cho phép property binding ngoài ý định sau constructor binding.** Với các object mutable, hãy dùng DTO đầu vào chuyên biệt; Spring MVC có thể tiếp tục property binding nếu không giới hạn.
12. **Nhầm `@RequestBody` với constructor binding của `DataBinder`.** Jackson deserialization và lỗi parse JSON có pipeline riêng.
13. **Tự nhận rằng `close()` sẽ gọi validator.** `close()` chỉ đọc trạng thái lỗi đã có; validate phải được kích hoạt riêng.
14. **Giả định object không tạo được thì mất mọi lỗi người dùng.** `BindingResult` có thể giữ `FieldError` và giá trị field đã ghi nhận.
15. **Phụ thuộc vào constructor ném exception để xây thông điệp người dùng.** Thiết kế lỗi validation có cấu trúc nếu cần phản hồi ổn định theo field.

## 13. Bộ test nên có

| Ca | Input | Điều cần xác nhận |
| --- | --- | --- |
| Valid | `name=Lan&age=20` | Không lỗi; target thuộc đúng kiểu và mang giá trị đã chuyển đổi |
| Wrong type | `age=abc` | `BindingResult.hasErrors()` true; field `age` có `typeMismatch` |
| Nullable missing | Không gửi `age` | Kết quả theo hợp đồng, không nhầm mặc định với conversion error |
| Blank required | `name=""` | Constraint validation hoặc guard được phản ánh đúng nhánh |
| Constructor throws | Guard ném `IllegalArgumentException` | Bắt/ánh xạ `BeanInstantiationException` khi áp dụng |
| Nested wrong type | `address.zip=oops` | Lỗi giữ đúng path của tham số lồng |
| Field conversion successful but domain invalid | `age=-2` | Phân biệt lỗi conversion với lỗi nghiệp vụ/constraint |
| Multiple conversion failures | Nhiều field có giá trị sai | Kiểm số FieldError và path, không giả định chỉ có một lỗi |
| Name mismatch | Gửi alias sai tên | Xác nhận hành vi của `@BindParam` hoặc `NameResolver` |
| Sensitive rejected value | Gửi field bí mật bị lỗi | Response/log không lộ raw value |
| Validator not invoked | Construct xong nhưng chưa gọi validation | Không mặc định constructor-binding đồng nghĩa Bean Validation đã chạy |
| Controller path | Có/không có `BindingResult` ngay sau `@ModelAttribute` | Xác nhận error handling và HTTP status |
| JSON body path | JSON sai kiểu với `@RequestBody` | Xác nhận exception từ message conversion không bị gán nhầm cho DataBinder |

Không chỉ test `getTarget() == null`; test phải kiểm cả **mã lỗi**, **field path**, **rejected value khi được phép**, **phân biệt lỗi conversion với constructor exception**, **trạng thái object có thực sự hợp lệ hay không**, và cách caller phản hồi.

## 14. Checklist xử lý an toàn trong service và controller

1. Nhận dữ liệu vào ở DTO/command rõ ràng; không expose trực tiếp entity hoặc field đặc quyền.
2. Với constructor binding, kiểm đúng tên argument, path lồng và conversion service; pin Spring version khi cần tái lập hành vi.
3. Gọi `construct(...)` bên trong ranh giới có xử lý ngoại lệ khởi tạo phù hợp.
4. Nếu `construct(...)` hoàn tất, lấy `BindingResult` và kiểm `hasErrors()` **trước** khi dùng target.
5. Khi lỗi chuyển kiểu, báo field và mã lỗi; đừng gọi domain logic với dữ liệu chưa hợp lệ.
6. Nếu constructor ném exception, tách lỗi cấu hình/lập trình khỏi lỗi do input; không trả stack trace hoặc secret cho client.
7. Kích hoạt Bean Validation/custom validator khi yêu cầu; không giả định nó tự chạy trong mọi lời gọi binder.
8. Khi cần lỗi HTTP ổn định, ánh xạ `MethodArgumentNotValidException`/`HandlerMethodValidationException` và các lỗi khác theo loại thật.
9. Sau khi dữ liệu hợp lệ, áp quy tắc service/domain và transaction phù hợp; binder không cam kết dữ liệu đã đáp ứng mọi invariant.
10. Viết test bao phủ cả success, type mismatch, missing, constructor guard, nested path và bảo mật rejected values.

### Sơ đồ quyết định cuối cùng

~~~text
construct(ValueResolver)
        |
        +-- throws exception? ----- YES ---> Phân loại exception khởi tạo/cấu hình
        |                                   Không mặc định ép thành FieldError
        |
        NO
        |
        v
BindingResult result = binder.getBindingResult()
        |
        +-- result.hasErrors()? ---- YES ---> Duyệt FieldError/ObjectError
        |                                   Trả lỗi, không dùng target cho domain
        |
        NO
        |
        v
target = binder.getTarget()
        |
        +-- target == null? ------- YES ---> Không có object hợp lệ: xử lý riêng
        |
        NO
        |
        v
Validation/authorization/domain checks theo contract
        |
        v
Thực hiện nghiệp vụ
~~~

**Ghi nhớ:** `BindingResult` là bộ nhớ lỗi có cấu trúc của lần binding; `BeanInstantiationException` là một khả năng thất bại của quá trình khởi tạo. Dùng kết quả **và** phân loại ngoại lệ đúng lúc, không gộp mọi trường hợp thành “không tạo được object” hoặc “chắc chắn có typeMismatch”.

## Tài liệu chính thức

- [Spring Framework 6.2 — Data Binding / Constructor Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beans-beans.html)
- [Spring Framework 6.2 — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.2 — DataBinder.ValueResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/DataBinder.ValueResolver.html)
- [Spring Framework 6.2 — BindingResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework 6.2 — Spring MVC @ModelAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
