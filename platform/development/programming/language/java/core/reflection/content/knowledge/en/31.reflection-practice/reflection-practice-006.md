# Xây dựng bộ kiểm tra annotation runtime đơn giản bằng Java Reflection

## 1. Mục tiêu thực hành và phạm vi

Bài này xây dựng **một bộ kiểm tra dữ liệu object (runtime validator) tối giản**, dùng annotation để khai báo quy tắc ngay trên field và Reflection để thực thi những quy tắc đó lúc chương trình chạy.

Yêu cầu đầu ra:

1. Định nghĩa annotation `@NotBlank` cho trường kiểu `String`: giá trị không được `null`, rỗng hoặc chỉ gồm ký tự trắng theo `String.isBlank()`.
2. Định nghĩa annotation `@MinValue(18)` cho trường kiểu `int` hoặc `Integer`: giá trị không được nhỏ hơn ngưỡng; đối với `Integer`, `null` được xem là không hợp lệ trong ví dụ.
3. Dùng Reflection đọc annotation và giá trị field, tạo danh sách lỗi có thể hiển thị cho người dùng.
4. Kiểm tra cả field được khai báo trong **lớp cha**, không chỉ lớp runtime trực tiếp.
5. Không phụ thuộc thứ tự trả về của `getDeclaredFields()`: sắp xếp lỗi trước khi in để kết quả test ổn định.
6. Phân biệt metadata được giữ ở **`RetentionPolicy.RUNTIME`** với annotation chỉ có `RetentionPolicy.CLASS`.
7. Tạo một chương trình **Java 17+ đầy đủ, biên dịch và chạy được**, không cần thư viện bên ngoài.

Đây là **bài thực hành thiết kế validator**: chỉ nhận một object đã có, kiểm tra field có annotation và trả danh sách lỗi. Đây **không** phải bộ quét classpath, engine validation tổng quát, hay bản thay thế cho chuẩn Jakarta Bean Validation.

## 2. Annotation là metadata, không tự thực thi quy tắc

Annotation khai báo thông tin gắn vào thành phần chương trình. Ví dụ:

```java
// Các ví dụ minh họa; định nghĩa hoàn chỉnh nằm ở phần chương trình.
@NotBlank(message = "name is required")
private final String name;

@MinValue(18)
private final Integer age;
```

Hai khai báo trên **không khiến JVM tự động kiểm tra dữ liệu**. Cần code đọc annotation và áp quy tắc lên giá trị của field. Vì vậy bài gồm hai phần khác nhau:

- **Phần metadata:** annotation mô tả yêu cầu, ví dụ `message` hoặc `value`.
- **Phần engine:** validator duyệt field, dùng `Field.getAnnotation(...)`, đọc giá trị field bằng `Field.get(...)`, rồi thêm thông báo lỗi khi quy tắc không đạt.

Annotation không bị giới hạn chỉ ở field: Java hỗ trợ nhiều `ElementType` như `TYPE`, `METHOD`, `PARAMETER`, `CONSTRUCTOR` và `TYPE_USE`. Ở bài này ta cố ý chọn `FIELD`, vì dữ liệu cần kiểm tra nằm trong các field của object.

## 3. Ba meta-annotation quan trọng

### `@Retention(RetentionPolicy.RUNTIME)`

Đây là điều kiện quan trọng nhất khi muốn dùng **runtime reflection** để đọc một annotation trên thành phần đã gắn nó:

- `SOURCE`: tồn tại trong mã nguồn, không bắt buộc được ghi vào class file.
- `CLASS`: được ghi vào class file theo chính sách lưu giữ tương ứng, nhưng **không khả kiến qua API annotation reflection thông thường** tại runtime.
- `RUNTIME`: class file giữ annotation ở dạng runtime-visible phù hợp và Reflection có thể đọc nó lúc chạy.

Nếu quên ghi `@Retention`, chính sách mặc định của annotation là **`RetentionPolicy.CLASS`**, nên `field.getAnnotation(MyRule.class)` thường trả `null` dù khi đọc mã nguồn bạn thấy `@MyRule`.

### `@Target(ElementType.FIELD)`

Ràng buộc annotation chỉ được gắn vào field. Compiler sẽ báo lỗi nếu cố gắn `@NotBlank` lên class hay method trong khi target chỉ cho `FIELD`. Tuy nhiên, `@Target(FIELD)` **không tự giới hạn kiểu field**: annotation vẫn có thể được gắn nhầm vào field `Integer`. Engine phải tự kiểm tra kiểu trường để tránh áp quy tắc không có ý nghĩa.

### Thành phần (element) của annotation

`@NotBlank(message = "...")` cho phép cấu hình thông báo; `@MinValue(18)` lưu ngưỡng kiểm tra qua phần tử `int value()`. Phần tử tên `value` có cú pháp rút gọn: `@MinValue(18)` tương đương `@MinValue(value = 18)`.

Một annotation có thể có giá trị mặc định (ví dụ `String message() default "must not be blank";`). Những giá trị này là **metadata của annotation**, không phải state riêng mà JVM tự thêm vào object được gắn annotation.

## 4. Các API Reflection sẽ dùng

| API | Vai trò trong validator | Lưu ý |
| --- | --- | --- |
| `obj.getClass()` | Lấy lớp runtime của object cần kiểm tra | `obj == null` phải được xử lý trước |
| `Class.getDeclaredFields()` | Lấy field khai báo trực tiếp trong từng lớp | Không tự lấy field từ superclass; thứ tự không bảo đảm |
| `Class.getSuperclass()` | Lần lượt duyệt các lớp cha | Dừng trước `Object.class` |
| `Field.getAnnotation(NotBlank.class)` | Lấy instance annotation, hoặc `null` nếu không có | Cần retention `RUNTIME` để đọc |
| `Field.isAnnotationPresent(...)` | Kiểm tra một annotation có hiện diện không | Không thay thế việc lấy các element của annotation |
| `Field.getType()` | Xác định kiểu khai báo của field | `String.class`, `int.class`, `Integer.class` là các kiểu khác nhau |
| `Field.get(Object)` | Đọc giá trị một field trên instance | Có thể gặp `IllegalAccessException` nếu không đủ quyền |
| `Field.canAccess(Object)` | Kiểm tra quyền truy cập hiện tại vào field đối với receiver | Phân biệt public/private; receiver phải phù hợp |
| `Field.trySetAccessible()` | Thử mở truy cập vào field khi chưa có quyền | Có thể không được phép bởi JPMS/security; không bảo đảm thành công |

Cùng một annotation type có thể được đọc bằng `getAnnotation` hoặc `getDeclaredAnnotation`. Trên **field**, việc duyệt từng field rõ ràng giúp tránh nhầm với inheritance: `@Inherited` chỉ áp dụng theo quy tắc đối với annotation trên **class**, không tự truyền annotation của field lớp cha xuống field cùng tên ở lớp con. Do đó, engine duyệt cả hierarchy theo `getSuperclass()` thay vì tin rằng `getDeclaredFields()` sẽ bao gồm trường kế thừa.

**Cách thiết kế ví dụ:** field `static` và field synthetic bị bỏ qua vì ta đang kiểm tra **trạng thái riêng của một instance**, không phải dữ liệu cấp lớp hoặc thành viên do compiler sinh. Với field cùng tên bị che khuất giữa lớp cha/con, tiền tố tên lớp khai báo trong thông báo giúp phân biệt hai trường.

## 5. Chương trình Java 17+ hoàn chỉnh

Tạo tệp `RuntimeAnnotationValidatorDemo.java`. Tất cả type nằm trong một file, không dùng package ngoài JDK:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface NotBlank {
    String message() default "must not be blank";
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface MinValue {
    int value();
}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.FIELD)
@interface CompileOnlyTag {}

public class RuntimeAnnotationValidatorDemo {
    static class Person {
        @NotBlank(message = "name is required")
        @CompileOnlyTag
        private final String name;

        @MinValue(18)
        private final Integer age;

        Person(String name, Integer age) {
            this.name = name;
            this.age = age;
        }
    }

    static class Employee extends Person {
        @NotBlank
        private final String department;

        Employee(String name, Integer age, String department) {
            super(name, age);
            this.department = department;
        }
    }

    static class Validator {
        static List<String> validate(Object object) {
            Objects.requireNonNull(object, "object");

            List<String> errors = new ArrayList<>();
            for (Class<?> type = object.getClass();
                    type != null && type != Object.class;
                    type = type.getSuperclass()) {
                for (Field field : type.getDeclaredFields()) {
                    if (field.isSynthetic()
                            || Modifier.isStatic(field.getModifiers())) {
                        continue;
                    }

                    NotBlank notBlank =
                            field.getAnnotation(NotBlank.class);
                    MinValue minValue =
                            field.getAnnotation(MinValue.class);
                    if (notBlank == null && minValue == null) {
                        continue;
                    }

                    if (notBlank != null && field.getType() != String.class) {
                        throw new IllegalArgumentException(
                                "@NotBlank requires String: " + field);
                    }
                    if (minValue != null
                            && field.getType() != int.class
                            && field.getType() != Integer.class) {
                        throw new IllegalArgumentException(
                                "@MinValue requires int/Integer: " + field);
                    }

                    if (!field.canAccess(object) && !field.trySetAccessible()) {
                        throw new IllegalStateException(
                                "Cannot read annotated field: " + field);
                    }

                    Object value;
                    try {
                        value = field.get(object);
                    } catch (IllegalAccessException e) {
                        throw new IllegalStateException(
                                "Cannot read annotated field: " + field, e);
                    }

                    String location =
                            type.getSimpleName() + "." + field.getName();
                    if (notBlank != null
                            && (value == null || ((String) value).isBlank())) {
                        errors.add(location + ": " + notBlank.message());
                    }
                    if (minValue != null
                            && (value == null
                                || ((Integer) value).intValue()
                                   < minValue.value())) {
                        errors.add(location + ": must be >= "
                                + minValue.value());
                    }
                }
            }
            Collections.sort(errors);
            return List.copyOf(errors);
        }
    }

    public static void main(String[] args) throws Exception {
        Field name = Person.class.getDeclaredField("name");
        System.out.println("RUNTIME visible: "
                + name.isAnnotationPresent(NotBlank.class));
        System.out.println("CLASS visible: "
                + name.isAnnotationPresent(CompileOnlyTag.class));

        Employee valid = new Employee("An", 20, "Engineering");
        Employee invalid = new Employee("  ", 16, null);

        System.out.println("Valid: "
                + Validator.validate(valid).isEmpty());

        List<String> errors = Validator.validate(invalid);
        System.out.println("Errors: " + errors.size());
        errors.forEach(System.out::println);
    }
}
```

Lệnh biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 RuntimeAnnotationValidatorDemo.java
java RuntimeAnnotationValidatorDemo
```

Kết quả dự kiến:

```text
RUNTIME visible: true
CLASS visible: false
Valid: true
Errors: 3
Employee.department: must not be blank
Person.age: must be >= 18
Person.name: name is required
```

### Giải thích từng phần

1. `@NotBlank` và `@MinValue` đều có `RetentionPolicy.RUNTIME`, nên `Field.getAnnotation(...)` đọc được cấu hình từ `Person` và `Employee` tại runtime. `@CompileOnlyTag` chỉ có `CLASS`, nên `isAnnotationPresent(CompileOnlyTag.class)` trả `false`.
2. Validator nhận một object đã tồn tại, không quét classpath. Nó bắt đầu từ `object.getClass()`, rồi dùng `getSuperclass()` để đọc cả `Employee` và `Person`. Nếu chỉ dùng `Employee.class.getDeclaredFields()`, sẽ bỏ sót `name` và `age`.
3. Khi tìm thấy annotation, validator kiểm tra field type trước. Điều này ngăn dùng `@NotBlank` lên số hoặc `@MinValue` lên chuỗi mà không được xử lý; lỗi cấu hình annotation được báo tách khỏi lỗi dữ liệu.
4. `canAccess`/`trySetAccessible` cho phép đọc các field `private` trong ví dụ chạy trên classpath thông thường. Việc truy cập này **không được bảo đảm** với mọi lớp/module; trình kiểm tra phải báo lỗi rõ nếu không có quyền.
5. `String.isBlank()` trả `true` cho chuỗi rỗng hoặc chỉ có whitespace theo `Character.isWhitespace`; ví dụ dùng `"  "` để tạo lỗi tên. `Integer` bằng `null` cũng bị coi là không đạt `@MinValue` theo hợp đồng của bài này.
6. `Collections.sort(errors)` làm cho output không phụ thuộc thứ tự các field mà Reflection trả về; tiền tố `Person.`/`Employee.` giúp chỉ rõ nơi khai báo trường.
7. `List.copyOf(errors)` trả một danh sách bất biến để bên gọi không vô ý sửa danh sách lỗi sau khi validator hoàn tất. Validator không sửa giá trị field, không tạo instance và không gọi method nghiệp vụ.

**Kết quả “Valid: true” chỉ có nghĩa object thỏa hai loại quy tắc được triển khai ở đây.** Nó không chứng nhận object hợp lệ cho mọi ràng buộc nghiệp vụ, dữ liệu nhạy cảm, hay toàn bộ đồ thị object lồng nhau.

## 6. Vì sao phải tách lỗi cấu hình khỏi lỗi dữ liệu?

Giả sử ai đó gắn `@NotBlank` lên field `Integer`. Annotation có target `FIELD` nên compiler **không cấm** điều này, nhưng code kiểm tra chuỗi bằng `isBlank()` sẽ không có ý nghĩa. Validator cần một chính sách:

- **Lỗi cấu hình:** annotation đặt sai kiểu, metadata bị hỏng, thiếu quyền đọc field hoặc lớp/module không tương thích. Ví dụ chọn fail-fast bằng `IllegalArgumentException` hoặc `IllegalStateException`, không xem đây là lỗi do người nhập.
- **Lỗi dữ liệu:** field có kiểu phù hợp, đọc thành công nhưng không đạt quy tắc (`name` toàn khoảng trắng, `age` dưới 18). Các lỗi này được thu thập vào `List<String>` để bên gọi hiển thị hoặc trả về API.
- **Đối tượng `null`:** ví dụ dùng `Objects.requireNonNull(object, "object")` và xem đây là lỗi gọi API, không phải đối tượng cần kiểm tra.

Chính sách này quan trọng vì nếu gộp tất cả thành “giá trị không hợp lệ”, framework có thể che giấu bug cấu hình hoặc lỗi truy cập reflection. Trong code production, nên có kiểu kết quả giàu cấu trúc hơn chuỗi, chẳng hạn record `ValidationError(String fieldPath, String code, String message)`, để hỗ trợ i18n, sắp xếp và hiển thị giao diện.

## 7. Kiểm thử cần bao phủ những trường hợp nào?

| Ca thử | Dữ liệu/cấu hình | Kỳ vọng |
| --- | --- | --- |
| Annotation runtime hiển thị | Field có `@Retention(RUNTIME)` | `isAnnotationPresent` trả `true` |
| Annotation chỉ lưu trong class file | Field có `@Retention(CLASS)` | API annotation runtime trả `false` |
| Object hợp lệ | `name="An"`, `age=20`, `department="Engineering"` | Danh sách lỗi rỗng |
| Chuỗi toàn khoảng trắng | `name="  "` | Một lỗi `@NotBlank` cho `name` |
| Giá trị thấp hơn ngưỡng | `age=16` với `@MinValue(18)` | Một lỗi ngưỡng tuổi |
| Giá trị wrapper `null` | `age=null` | Một lỗi `@MinValue` |
| String `null` | `department=null` | Một lỗi `@NotBlank` |
| Field từ superclass | `name` và `age` khai báo trong `Person` | Vẫn được kiểm tra qua vòng lặp class hierarchy |
| Annotation gắn nhầm kiểu | `@NotBlank int count` | Báo lỗi cấu hình, không xem là input sai |
| Không đủ quyền đọc | Field private thuộc module không mở | Báo lỗi truy cập, không giả vờ kiểm tra thành công |
| Field static hoặc synthetic | Không phải dữ liệu instance bình thường | Bỏ qua theo hợp đồng hiện tại |
| Không có annotation được hỗ trợ | Field dữ liệu khác | Bỏ qua; không tự suy diễn thêm quy tắc |

Khi mở rộng bài kiểm thử, có thể thêm `check(...)` hoặc unit test JUnit, nhưng cần phân biệt *việc annotation có hiện diện* và *engine thực thi quy tắc đúng*. Một annotation mới được thêm vào mã nguồn mà validator chưa có nhánh xử lý sẽ không tự tạo hiệu lực.

## 8. Giới hạn cần biết trước khi đưa vào ứng dụng thật

### Truy cập private và Java modules

Trên classpath thông thường, `trySetAccessible()` có thể thành công với các lớp do ứng dụng sở hữu, như ví dụ trên. Với **named modules** trong JPMS, quyền deep reflection có thể bị chặn nếu package chưa được `opens` cho module gọi. `getDeclaredFields()` có thể liệt kê metadata nhưng `Field.get` vẫn không được phép. Không mặc định dùng `setAccessible(true)` sẽ vượt được mọi ranh giới module.

Thư viện thường ưu tiên public accessor/getter hoặc những hợp đồng module rõ ràng nếu cần kiểm tra object thuộc package của bên khác. Nếu không đọc được field, kết quả phải báo lỗi truy cập thay vì im lặng bỏ qua rồi kết luận object hợp lệ.

### Retention, kế thừa và trường bị ẩn

- `@Inherited` **chỉ ảnh hưởng tìm annotation trên class theo cơ chế hỗ trợ**, không làm một field lớp cha “chuyển” annotation xuống field mới của lớp con.
- `getDeclaredFields()` không tự bao gồm field kế thừa, nên vòng lặp `getSuperclass()` là có chủ đích.
- Nếu subclass khai báo field trùng tên với superclass, hai field vẫn là hai thành viên khác nhau. Tiền tố tên class trong thông báo lỗi giúp tránh nhầm.
- Interface không có field instance theo nghĩa thông thường (field trong interface mặc định `public static final`); engine bài này chỉ kiểm tra instance fields của chuỗi superclass, không dò interface.

### Null, kiểu số và dữ liệu tổng quát

`@MinValue` trong bài này hỗ trợ **chỉ `int`/`Integer`**: `Field.get(...)` boxing primitive `int` thành `Integer`, cho phép một đoạn so sánh chung. `long`, `BigDecimal`, `double`, field generic hay tập hợp cần chính sách so sánh riêng; không nên ép mọi `Number` sang `int` vì có thể mất độ chính xác hoặc làm sai nghĩa.

`@NotBlank` dùng `String.isBlank()`, không tương đương kiểm tra string chứa email hợp lệ, không đảm bảo chuẩn hóa Unicode cho mọi nghiệp vụ và không xử lý trimming/mutation. Engine **chỉ đọc**, không thay đổi object.

### Hiệu năng, vòng đời, thread safety

Mỗi lần gọi hiện tại duyệt class hierarchy, phản chiếu field, đọc annotation và truy cập dữ liệu. Khi kiểm tra hàng triệu object cùng lớp, một thư viện có thể cache **metadata bất biến** theo class (ví dụ danh sách field, annotation và cách đọc) để giảm overhead; tuyệt đối không cache **giá trị** field của một object làm kết quả cho object khác.

Trong ví dụ, `List<String> errors` được tạo cục bộ cho mỗi lời gọi nên không dùng state lỗi tĩnh chia sẻ. Điều đó tránh race trên danh sách lỗi nhưng **không làm object được kiểm tra tự động thread-safe**: nếu thread khác sửa dữ liệu cùng lúc, kết quả có thể phản ánh trạng thái không nhất quán.

### Bảo mật và thiết kế API

Việc mở quyền đọc field riêng tư là hoạt động nhạy cảm. Không dùng bài này để đọc object không thuộc quyền kiểm soát, không log giá trị bí mật và không tin mọi annotation đến từ bytecode bên thứ ba. Nếu ứng dụng nhận dữ liệu không tin cậy, validator chỉ là **một lớp kiểm tra**, không thay cho authentication, authorization, ràng buộc nghiệp vụ và an toàn deserialization.

### Khi nào dùng thư viện chuẩn hóa?

Với ứng dụng thật có kiểm tra bean phức tạp, nested objects, group validation, message localization, lifecycle và framework integration, cân nhắc **Jakarta Bean Validation** với implementation phù hợp thay vì tiếp tục mở rộng validator tự viết. Annotation tùy biến `@NotBlank` và `@MinValue` ở đây là **quy tắc minh họa riêng**, không phải chính xác các annotation và toàn bộ hợp đồng của Jakarta Validation.

## 9. Từng bước mở rộng có kiểm soát

1. **Thêm một annotation mới:** ví dụ `@MaxLength(int value)` cho `String`. Khai báo `@Target(FIELD)` và `@Retention(RUNTIME)`; sau đó thêm nhánh đọc và áp quy tắc trong validator.
2. **Tạo cấu trúc lỗi:** thay `String` bằng một record chứa đường dẫn trường, mã lỗi và thông báo. Kiểm thử thứ tự và tình huống cùng field vi phạm nhiều quy tắc.
3. **Hỗ trợ annotation lặp:** chỉ khi thực sự cần, dùng `@Repeatable` và API `getAnnotationsByType(...)` phù hợp; đừng mặc định `getAnnotation` trả mọi giá trị lặp.
4. **Thêm nested validation:** định nghĩa `@ValidNested` riêng, duyệt object con và mảng/collection với chính sách giới hạn độ sâu, phát hiện chu trình bằng identity set và tránh stack overflow.
5. **Cache metadata:** lưu danh sách field/rule đã kiểm tra theo `Class<?>` bằng cơ chế cache có tính đến vòng đời class loader; tránh memory leak khi plugin có thể unload.
6. **Viết unit test âm:** sai loại field, private field không mở bởi module, `null`, Unicode whitespace, inheritance, field static/synthetic và lỗi handler.

Mỗi bước đều phải trả lời: metadata đến từ đâu, khi nào đọc được, lỗi cấu hình xử lý ra sao, và engine có thực hiện đúng quy tắc không. Annotation **không phải magic**; giá trị nằm ở cơ chế đọc và kiểm thử.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao gắn `@NotBlank` nhưng không chạy validator lại không tự chặn một `String` rỗng?

**Đáp án:** Annotation chỉ cung cấp metadata. Cần code lấy annotation và thực thi ràng buộc mới có tác dụng.

**Câu 2.** Nếu `@Retention` không khai báo, `Field.getAnnotation(...)` sẽ đọc được annotation đó mặc định không?

**Đáp án:** Không nên kỳ vọng. Retention mặc định là `CLASS`, không khả kiến qua annotation reflection bình thường tại runtime; dùng `RUNTIME` nếu phải đọc bằng `Field.getAnnotation`.

**Câu 3.** `@Target(FIELD)` có ngăn lập trình viên đặt `@NotBlank` lên field `int` không?

**Đáp án:** Không. `@Target` giới hạn **loại phần tử khai báo** (field), không kiểm tra kiểu dữ liệu Java của field. Validator phải kiểm tra `Field.getType()` và báo lỗi cấu hình khi sai.

**Câu 4.** Tại sao `Employee.class.getDeclaredFields()` không đủ để kiểm tra trường `name` khai báo trong `Person`?

**Đáp án:** `getDeclaredFields()` chỉ lấy field được khai báo trong `Employee`. Phải duyệt `getSuperclass()` để đọc field lớp cha nếu hợp đồng muốn bao phủ chúng.

**Câu 5.** Tại sao cần `Collections.sort(errors)` trước khi so sánh stdout trong test?

**Đáp án:** API Reflection không cam kết thứ tự trả về field; sắp xếp thông báo làm output xác định và tránh test phụ thuộc thứ tự không được bảo đảm.

**Câu 6.** Có phải `trySetAccessible()` chắc chắn mở được mọi private field khi chạy ứng dụng Java 17+?

**Đáp án:** Không. JPMS, security và quyền truy cập có thể chặn. Khi không được phép, validator phải báo lỗi truy cập và không tự kết luận object hợp lệ.

**Câu 7.** Khi `age` là `Integer` bằng `null`, `@MinValue(18)` xử lý ra sao theo ví dụ?

**Đáp án:** Không hợp lệ vì bài này chọn null bị coi là vi phạm `@MinValue`; library khác có thể chọn null là hợp lệ cho ràng buộc min và yêu cầu một annotation `@NotNull` riêng. Cần tài liệu hóa chính sách.

**Kết luận:** Bộ kiểm tra annotation runtime gồm **khai báo ràng buộc (`RUNTIME`/`FIELD`) → đọc metadata bằng Reflection → truy cập dữ liệu → đánh giá quy tắc → báo lỗi có cấu trúc**. Việc tách lỗi cấu hình khỏi lỗi dữ liệu, xử lý kế thừa và access control rõ ràng giúp bài thực hành trở thành nền tảng tốt trước khi dùng các validation framework đầy đủ.