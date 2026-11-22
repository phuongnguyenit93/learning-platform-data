# Xây dựng bộ kiểm tra dữ liệu dựa trên annotation

## 1. Từ nhãn mô tả đến hành vi kiểm tra

Giả sử dữ liệu đăng ký cần tên không trống và tuổi nằm trong một khoảng. Viết câu lệnh kiểm tra riêng ở mọi nơi dễ lặp quy tắc; gắn annotation lên trường giúp đặt **mô tả ràng buộc** gần dữ liệu.

Tuy nhiên, annotation không tự kiểm tra gì. Ta cần một bộ đọc thực hiện chuỗi:

```text
Đối tượng dữ liệu
    → tìm các trường có annotation
    → đọc cấu hình ràng buộc
    → lấy giá trị trường
    → áp dụng quy tắc
    → trả danh sách vi phạm
```

Ví dụ trong bài dùng Java 17 trở lên, không cần thư viện ngoài. Mục tiêu là hiểu đầy đủ cách annotation lúc chạy kết hợp với reflection để tạo hành vi kiểm tra dữ liệu.

## 2. Chốt hợp đồng trước khi viết mã

Bộ kiểm tra hỗ trợ hai annotation tự định nghĩa:

| Annotation | Kiểu trường hỗ trợ | Quy tắc |
| --- | --- | --- |
| `@RequiredText` | `String` | Không được `null`, rỗng hoặc chỉ chứa ký tự trắng theo `String.isBlank()` |
| `@IntRange(min, max)` | `int`, `Integer` | Nếu có giá trị thì phải nằm trong đoạn đóng `[min, max]` |

Các lựa chọn thiết kế của ví dụ:

- `Integer` mang giá trị `null` được bỏ qua khi chỉ có `@IntRange`. Ràng buộc khoảng và yêu cầu bắt buộc có dữ liệu là hai quy tắc khác nhau.
- `int` không thể là `null`; số 0 là giá trị thực và vẫn phải được kiểm tra.
- Chỉ xét trường đối tượng được gắn các annotation trên; trường `static` có ràng buộc bị coi là cấu hình sai.
- Xét cả trường khai báo trong lớp cha; bỏ qua trường synthetic do trình biên dịch sinh.
- Thu thập mọi vi phạm dữ liệu, không dừng ở vi phạm đầu tiên.
- Kiểu trường không hỗ trợ hoặc `min > max` là lỗi cấu hình của người lập trình, không phải lỗi dữ liệu của người dùng.

`String.isBlank()` kiểm tra chuỗi rỗng hoặc chỉ gồm các mã ký tự được Java xem là whitespace; nó không tự sửa hay cắt chuỗi đầu vào. [API String.isBlank](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#isBlank())

Hai tên annotation ở đây là hợp đồng riêng của chương trình. Không suy luận rằng chỉ cần một annotation có tên tương tự từ thư viện khác thì bộ đọc này sẽ tự hiểu nó.

## 3. Chương trình chạy đầy đủ

Lưu toàn bộ mã vào **AnnotationValidatorDemo.java**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class AnnotationValidatorDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.FIELD)
    public @interface RequiredText {
        String message() default "must not be blank";
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.FIELD)
    public @interface IntRange {
        int min();
        int max();
        String message() default "must be in";
    }

    public record Violation(String field, String message) {
        @Override
        public String toString() {
            return field + ": " + message;
        }
    }

    public static final class MiniValidator {
        private MiniValidator() {
        }

        public static List<Violation> validate(Object bean) {
            if (bean == null) {
                throw new IllegalArgumentException(
                        "bean must not be null");
            }

            List<Violation> violations = new ArrayList<>();

            for (Field field : fieldsOf(bean.getClass())) {
                RequiredText text =
                        field.getDeclaredAnnotation(RequiredText.class);
                IntRange range =
                        field.getDeclaredAnnotation(IntRange.class);

                if (text == null && range == null) {
                    continue;
                }

                checkConfiguration(field, text, range);
                Object value = readValue(field, bean);
                String path = fieldPath(field);

                if (text != null
                        && (value == null
                            || ((String) value).isBlank())) {
                    violations.add(new Violation(
                            path, text.message()));
                }

                if (range != null && value != null) {
                    int number = (Integer) value;
                    if (number < range.min()
                            || number > range.max()) {
                        String message = range.message()
                                + " [" + range.min()
                                + ", " + range.max() + "]";
                        violations.add(new Violation(path, message));
                    }
                }
            }

            return List.copyOf(violations);
        }

        private static void checkConfiguration(
                Field field, RequiredText text, IntRange range) {
            String path = fieldPath(field);

            if (Modifier.isStatic(field.getModifiers())) {
                throw new IllegalStateException(
                        "constraint on static field " + path);
            }

            if (text != null && field.getType() != String.class) {
                throw new IllegalStateException(
                        "RequiredText requires String on " + path);
            }

            if (range != null) {
                Class<?> type = field.getType();
                if (type != int.class && type != Integer.class) {
                    throw new IllegalStateException(
                            "IntRange requires int or Integer on "
                                    + path);
                }

                if (range.min() > range.max()) {
                    throw new IllegalStateException(
                            "invalid range on " + path);
                }
            }
        }

        private static Object readValue(Field field, Object bean) {
            if (!field.canAccess(bean)
                    && !field.trySetAccessible()) {
                throw new IllegalStateException(
                        "cannot access " + fieldPath(field));
            }

            try {
                return field.get(bean);
            } catch (IllegalAccessException ex) {
                throw new IllegalStateException(
                        "cannot read " + fieldPath(field), ex);
            }
        }

        private static List<Field> fieldsOf(Class<?> beanType) {
            List<Field> fields = new ArrayList<>();

            for (Class<?> type = beanType;
                    type != null && type != Object.class;
                    type = type.getSuperclass()) {
                for (Field field : type.getDeclaredFields()) {
                    if (!field.isSynthetic()) {
                        fields.add(field);
                    }
                }
            }

            fields.sort(Comparator.comparing(
                    (Field field) ->
                            field.getDeclaringClass().getName()
                                    + "#" + field.getName()));
            return fields;
        }

        private static String fieldPath(Field field) {
            return field.getDeclaringClass().getSimpleName()
                    + "." + field.getName();
        }
    }

    static class BaseInput {
        @RequiredText
        private final String tenant;

        BaseInput(String tenant) {
            this.tenant = tenant;
        }
    }

    static class UserInput extends BaseInput {
        @RequiredText
        private final String name;

        @IntRange(min = 18, max = 120)
        private final Integer age;

        @IntRange(min = 0, max = 10)
        private final int retryLimit;

        UserInput(String name, Integer age, int retryLimit) {
            super("demo");
            this.name = name;
            this.age = age;
            this.retryLimit = retryLimit;
        }
    }

    static class MissingTenant extends BaseInput {
        MissingTenant() {
            super(" ");
        }
    }

    static class BadConfiguration {
        @IntRange(min = 10, max = 1)
        private int points = 5;
    }

    public static void main(String[] args) {
        System.out.println("valid=" + MiniValidator.validate(
                new UserInput("Lan", 25, 3)));
        System.out.println("invalid=" + MiniValidator.validate(
                new UserInput("  ", 17, 11)));
        System.out.println("optionalAge=" + MiniValidator.validate(
                new UserInput("Minh", null, 0)));
        System.out.println("inherited=" + MiniValidator.validate(
                new MissingTenant()));

        try {
            MiniValidator.validate(new BadConfiguration());
        } catch (IllegalStateException ex) {
            System.out.println("badConfig=" + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 AnnotationValidatorDemo.java
java AnnotationValidatorDemo
```

Kết quả chuẩn:

```text
valid=[]
invalid=[UserInput.age: must be in [18, 120], UserInput.name: must not be blank, UserInput.retryLimit: must be in [0, 10]]
optionalAge=[]
inherited=[BaseInput.tenant: must not be blank]
badConfig=invalid range on BadConfiguration.points
```

Dòng `invalid` chứa đủ ba vi phạm. Dòng `optionalAge` không có lỗi vì hợp đồng của `IntRange` cho phép `Integer` vắng giá trị. Dòng `inherited` cho thấy bộ đọc đã duyệt trường trong lớp cha. Dòng cuối là lỗi khai báo khoảng, nên không được đưa vào danh sách vi phạm dữ liệu.

## 4. Annotation phải được giữ lại đến lúc chạy

`@Retention(RetentionPolicy.RUNTIME)` cho phép bộ đọc lấy annotation qua reflection. Bỏ `@Retention` làm chính sách mặc định thành `CLASS`; bộ kiểm tra lúc chạy sẽ không thấy các annotation theo cách đọc đang dùng. [API Retention](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Retention.html)

`@Target(ElementType.FIELD)` giới hạn vị trí viết annotation. Nó không thể diễn đạt “chỉ được gắn lên trường String” hay “min không lớn hơn max”. Vì vậy, phần `checkConfiguration` vẫn cần kiểm tra tính hợp lệ của quy tắc.

Đây là khác biệt giữa hai lớp kiểm tra:

- Trình biên dịch kiểm tra vị trí và cú pháp annotation.
- Bộ kiểm tra tự định nghĩa kiểm tra hợp đồng sử dụng sâu hơn của annotation.

## 5. Duyệt trường và đọc giá trị

`getDeclaredFields()` chỉ trả trường khai báo trực tiếp trong một lớp. Chương trình chủ động đi lên bằng `getSuperclass()` để thu thập thêm trường lớp cha. Đây là thuật toán duyệt của bộ kiểm tra, không phải tác dụng của `@Inherited`. [API Class.getDeclaredFields](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html#getDeclaredFields())

Thứ tự trường trả về không được dùng như thứ tự mã nguồn. Bài sắp xếp theo tên lớp khai báo và tên trường để danh sách lỗi có thứ tự ổn định. Nếu lớp con che một trường cùng tên ở lớp cha, mỗi `Field` vẫn đại diện cho một khai báo riêng; nhãn chẩn đoán có tên lớp giúp người đọc phân biệt chúng.

`Field.get(bean)` lấy giá trị của trường trên đối tượng. Với trường `int`, kết quả được đóng gói thành `Integer`; vì bộ kiểm tra đã xác nhận kiểu trường chỉ là `int` hoặc `Integer`, phép ép kiểu trong quy tắc khoảng là có cơ sở. Không thay phần xác thực kiểu bằng việc ép mọi `Number` sang `int`, vì việc đó có thể làm mất phần thập phân hoặc thay đổi giá trị. [API Field.get](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Field.html#get(java.lang.Object))

### Đọc annotation khác đọc dữ liệu private

Đọc metadata annotation không cần thay quyền truy cập. Nhưng chương trình này còn lấy **giá trị trường**, nên cần xét quyền.

`canAccess(bean)` kiểm tra khả năng truy cập của bên gọi. Nếu cần, `trySetAccessible()` thử cho phép truy cập và có thể trả `false`, chẳng hạn khi ranh giới mô-đun Java không cho mở thành viên. Bộ kiểm tra báo lỗi rõ ràng khi không đọc được, không âm thầm bỏ trường rồi trả kết quả hợp lệ. Trong ví dụ một tệp, các lớp lồng cùng nhóm lớp có thể đã truy cập được trường private; không phải lần nào cũng cần thay trạng thái truy cập. [API AccessibleObject](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AccessibleObject.html#trySetAccessible())

Mã chỉ đọc giá trị, không gọi `Field.set`, nên dữ liệu đầu vào không bị sửa.

## 6. Phân biệt vi phạm dữ liệu với lỗi cấu hình

| Tình huống | Cách xử lý trong ví dụ |
| --- | --- |
| Tên là `null` hoặc chuỗi trắng | Thêm một `Violation` |
| Tuổi có giá trị nằm ngoài khoảng | Thêm một `Violation` |
| Tuổi là `null` và chỉ có `IntRange` | Bỏ qua theo hợp đồng đã chọn |
| `RequiredText` gắn lên `Integer` | Ném lỗi cấu hình |
| `IntRange` gắn lên `String` hoặc `double` | Ném lỗi cấu hình |
| `min > max` | Ném lỗi cấu hình |
| Trường `static` có ràng buộc | Ném lỗi cấu hình |
| Không được quyền đọc trường có ràng buộc | Ném lỗi thực thi bộ kiểm tra |
| Đối tượng gốc là `null` | Ném `IllegalArgumentException` vì lời gọi không đúng hợp đồng |

Dữ liệu không hợp lệ là kết quả dự kiến của quy trình kiểm tra, nên trả một danh sách có cấu trúc. Cấu hình không hợp lệ là lỗi của chương trình: không nên biến nó thành thông báo yêu cầu người dùng sửa tên hay tuổi.

`List.copyOf(violations)` tạo danh sách kết quả không cho phép thêm, xóa hoặc thay phần tử. `Violation` là record chứa thông tin trường và thông báo, giúp bên gọi xử lý dữ liệu thay vì phân tích một chuỗi lỗi duy nhất. [API List.copyOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))

## 7. Gắn kiểm tra vào luồng xử lý

Có annotation trên lớp dữ liệu chưa đủ. Bên nhận dữ liệu phải gọi bộ kiểm tra trước bước cần dữ liệu hợp lệ. Đoạn sau minh họa bên trong một phương thức, dùng các kiểu của chương trình trên:

```java
UserInput input = new UserInput("Lan", 25, 3);
List<Violation> errors = MiniValidator.validate(input);

if (!errors.isEmpty()) {
    throw new IllegalArgumentException(errors.toString());
}

// Continue the operation only after validation succeeds.
```

Trong ứng dụng có giao diện, bên gọi có thể chuyển danh sách lỗi thành thông báo cho từng ô nhập thay vì ném ngoại lệ như đoạn minh họa. Điều cần giữ là quyết định xử lý được dựa trên danh sách trả về.

Bộ kiểm tra không tự chuẩn hóa dữ liệu. Nếu nghiệp vụ yêu cầu bỏ khoảng trắng ở hai đầu tên, hãy thiết kế bước chuẩn hóa riêng và thống nhất kiểm tra trước hay sau bước đó. Không vừa kiểm tra vừa âm thầm sửa dữ liệu đầu vào.

Kiểm tra một đối tượng cũng không tự bảo đảm quan hệ ngoài đối tượng, chẳng hạn mã người dùng chưa tồn tại trong cơ sở dữ liệu. Quy tắc cần trạng thái bên ngoài phải có thiết kế thực thi riêng.

## 8. Những giới hạn cần hiểu khi mở rộng

Ví dụ đã xử lý hai quy tắc trên trường và trường kế thừa. Nó chưa duyệt đệ quy đối tượng lồng, chưa kiểm tra từng phần tử collection, chưa hỗ trợ ràng buộc giữa hai trường, chưa có nhóm kiểm tra hay cơ chế quốc tế hóa thông báo.

Nếu bổ sung duyệt đệ quy, cần thiết kế đường dẫn lỗi và xử lý chu trình tham chiếu. Nếu bổ sung ràng buộc số, phải xác định kiểu số, độ chính xác và cách so sánh; không mặc nhiên mở rộng phép ép sang `Integer` cho mọi trường.

Khi số lượng quy tắc tăng, có thể tách mỗi quy tắc thành một thành phần xử lý thay vì kéo dài chuỗi `if` trong `validate`. Cần giữ việc kiểm tra cấu hình, chính sách `null` và cách thu thập lỗi nhất quán giữa các thành phần.

Với đối tượng có thể bị thay đổi đồng thời, danh sách lỗi chỉ phản ánh các giá trị đã đọc trong lần kiểm tra, không tự tạo một ảnh chụp nguyên tử của toàn bộ đối tượng. Dữ liệu bất biến hoặc một bước chụp dữ liệu rõ ràng giúp việc suy luận dễ hơn.

### Các lỗi thường gặp

- Quên `RUNTIME`, khiến bộ đọc không thấy ràng buộc.
- Chỉ dùng `getDeclaredFields()` trên lớp cuối cùng rồi bỏ sót dữ liệu lớp cha.
- Gọi `isBlank()` trước khi kiểm tra `null`.
- Không kiểm tra kiểu trường, khiến lỗi cấu hình biến thành `ClassCastException`.
- Coi `null` của mọi kiểu đều hợp lệ hoặc đều sai mà không định nghĩa chính sách.
- Bắt lỗi reflection rồi tiếp tục như thể trường đã được kiểm tra thành công.
- Chỉ tạo annotation nhưng không có điểm nào gọi `validate`.

### Tự thực hành

1. Kiểm tra các tuổi 18 và 120: vì sao đều hợp lệ? Đổi thành 17 và 121 rồi xác nhận lỗi.
2. Thay tên bằng `null`, `""`, `"\t\n"` và `" Lan "`. Giá trị nào bị từ chối theo đúng hợp đồng hiện tại?
3. Gắn `@RequiredText` lên trường `Integer`; vì sao cần báo lỗi cấu hình thay vì lỗi “must not be blank”?
4. Bổ sung một annotation yêu cầu giá trị tham chiếu khác `null`. Dùng nó cùng `IntRange` để làm tuổi bắt buộc, giữ nguyên ý nghĩa độc lập của từng quy tắc.
5. Thêm thông báo tùy chỉnh qua `message` và xác nhận đối tượng được kiểm tra không bị thay đổi.
6. Viết kiểm tra cho trường kế thừa, trường static có ràng buộc, khoảng khai báo sai và kiểu trường không hỗ trợ.
