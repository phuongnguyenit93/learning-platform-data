# Annotation không tự thực thi validation hay hành vi nghiệp vụ

## 1. Annotation là metadata, không phải lệnh tự chạy

Java annotation dùng để **gắn thông tin có cấu trúc** lên chương trình: class, field, method, constructor, parameter và các phần tử khác được `@Target` cho phép. Ví dụ:

~~~java
class Registration {
    @RequiredText
    String username;

    @Minimum(18)
    int age;
}
~~~

Đoạn code trên chỉ là minh họa, với hai annotation tự định nghĩa `@RequiredText` và `@Minimum` sẽ được trình bày đầy đủ trong ví dụ runnable phía dưới.

Khi class được tạo hoặc field được gán giá trị, Java **không tự động** đọc `@RequiredText`, tự kiểm tra chuỗi trắng, đọc `@Minimum(18)` rồi từ chối tuổi nhỏ hơn 18. Annotation chỉ mô tả một *quy tắc tiềm năng*. Muốn quy tắc đó có hiệu lực, **phải có thành phần hiểu metadata và thực thi hành vi**:

- Compiler hoặc annotation processor đọc annotation tại thời điểm biên dịch, khi được thiết kế để làm việc đó.
- Framework/container/runner đọc annotation ở runtime rồi gọi một validation engine, interceptor, mapper, test runner hoặc logic nghiệp vụ thích hợp.
- Chính ứng dụng dùng Reflection để tra cứu annotation và **chủ động** chạy mã kiểm tra/tác động.

Cần tách ba tầng khái niệm:

1. **Khai báo**: `@Minimum(18)` đính kèm giá trị 18 vào metadata.
2. **Đọc metadata**: `field.getAnnotation(Minimum.class)` trả thông tin annotation nếu nó có thể được truy cập ở runtime.
3. **Áp dụng quy tắc**: code đọc `minimum.value()`, so sánh giá trị field, quyết định chấp nhận/từ chối và xử lý hậu quả.

Chỉ có tầng 1 không tự sinh ra tầng 3. Ngay cả tầng 2 cũng không làm validation chạy nếu chương trình không dùng metadata để ra quyết định.

**Nói chính xác:** Bản thân một annotation tự định nghĩa không chứa cơ chế “kích hoạt khi giá trị thay đổi”. Java có một số annotation chuẩn được compiler hay công cụ hiểu theo nghĩa riêng, như `@Override` (compiler kiểm tra phương thức override) hoặc `@Deprecated` (cảnh báo sử dụng API). Đây vẫn là **công cụ khác xử lý metadata**, không phải annotation tự chạy một hàm validate ở runtime.

## 2. `@Retention(RUNTIME)` giúp đọc được annotation, nhưng không tạo hành vi

Để Reflection đọc được annotation từ class file, kiểu annotation thường cần `@Retention(RetentionPolicy.RUNTIME)`:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface RequiredText {
}
~~~

Đây là định nghĩa annotation có thể được Reflection đọc ở runtime; **nó chưa kiểm tra bất cứ giá trị nào**.

| Retention policy | Ý nghĩa | `getAnnotation(...)` runtime |
| --- | --- | --- |
| `SOURCE` | Annotation chỉ thuộc phạm vi mã nguồn, không lưu vào class file | Không thấy |
| `CLASS` | Annotation có thể nằm trong class file nhưng không được lưu để Reflection truy cập ở runtime | Không thấy |
| `RUNTIME` | Metadata được giữ để Reflection có thể tra cứu ở runtime | Có thể thấy nếu annotation tồn tại tại phần tử được tra cứu |

`@Target(ElementType.FIELD)` giới hạn vị trí được phép đặt `@RequiredText` lên **field**, không tuyên bố field nào bắt buộc phải chứa chuỗi khác rỗng. Nếu đặt nhầm lên method, compiler có thể từ chối vì `@Target`; đó là quy tắc cú pháp/metadata chứ không phải validation dữ liệu người dùng.

Khi một kiểu annotation không khai báo `@Retention`, mặc định là `RetentionPolicy.CLASS`. Vì thế, nếu viết annotation chỉ để runtime Reflection xử lý, cần xem rõ retention. Tuy nhiên, **`RUNTIME` chỉ là điều kiện để đọc metadata, không phải trigger** kích hoạt engine.

## 3. Ví dụ Java 17+ chạy độc lập: có annotation nhưng vẫn phải gọi validator

Tạo một file duy nhất tên **`AnnotationValidationDemo.java`**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface RequiredText {
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface Minimum {
    int value();
}

class Signup {
    @RequiredText
    public String username;

    @Minimum(18)
    public int age;

    Signup(String username, int age) {
        this.username = username;
        this.age = age;
    }
}

public class AnnotationValidationDemo {
    static List<String> validate(Object bean) throws IllegalAccessException {
        List<String> errors = new ArrayList<>();
        Field[] fields = bean.getClass().getDeclaredFields();

        // Thứ tự getDeclaredFields() không được bảo đảm.
        Arrays.sort(fields, Comparator.comparing(Field::getName));

        for (Field field : fields) {
            if (field.isAnnotationPresent(RequiredText.class)) {
                Object value = field.get(bean);
                if (!(value instanceof String text) || text.isBlank()) {
                    errors.add(field.getName() + ": required");
                }
            }

            Minimum minimum = field.getAnnotation(Minimum.class);
            if (minimum != null) {
                int value = field.getInt(bean);
                if (value < minimum.value()) {
                    errors.add(field.getName()
                            + ": minimum " + minimum.value());
                }
            }
        }
        return errors;
    }

    static void register(Signup signup) {
        // Chỉ mô phỏng một hành vi nghiệp vụ bằng cách in thông báo.
        System.out.println("registered username="
                + signup.username.trim() + ", age=" + signup.age);
    }

    public static void main(String[] args) throws Exception {
        Signup invalid = new Signup("  ", 16);

        System.out.println("annotation present: "
                + Signup.class.getDeclaredField("username")
                        .isAnnotationPresent(RequiredText.class));

        System.out.println("without validation:");
        register(invalid);

        List<String> errors = validate(invalid);
        System.out.println("errors: " + errors);
        if (errors.isEmpty()) {
            register(invalid);
        } else {
            System.out.println("rejected by explicit validator");
        }

        Signup valid = new Signup("Lan", 23);
        if (validate(valid).isEmpty()) {
            register(valid);
        }
    }
}
~~~

Từ thư mục chứa file, biên dịch và chạy:

~~~bash
javac --release 17 AnnotationValidationDemo.java
java AnnotationValidationDemo
~~~

Output:

~~~text
annotation present: true
without validation:
registered username=, age=16
errors: [age: minimum 18, username: required]
rejected by explicit validator
registered username=Lan, age=23
~~~

### Phân tích chính xác điều vừa xảy ra

1. `@RequiredText` và `@Minimum(18)` chỉ là các annotation đã khai báo trên hai field. Đối tượng `Signup("  ", 16)` vẫn được khởi tạo bình thường: constructor không tự gọi validator.
2. `isAnnotationPresent(RequiredText.class)` trả `true` vì annotation trên field có retention `RUNTIME`. **Nhưng phép đọc metadata này không kiểm tra giá trị `username`**.
3. `register(invalid)` được gọi trực tiếp **trước** khi validation. Nó vẫn chạy, dù `username` toàn khoảng trắng và `age` nhỏ hơn 18. Hàm `register` trong ví dụ chỉ in thông điệp; nếu là nghiệp vụ thật, đây có thể là điểm tạo dữ liệu sai.
4. Chỉ khi code chủ động gọi `validate(invalid)`, validator mới duyệt các field, tra cứu annotation, đọc giá trị bằng Reflection và thực hiện `if`/so sánh.
5. `Minimum.value()` trả giá trị cấu hình **18**; code `value < minimum.value()` mới là **điều kiện kiểm tra**. Nếu điều kiện đúng, validator chủ động thêm thông báo lỗi.
6. `RequiredText` không có member nào, nhưng validator quy ước rằng field được đánh dấu phải là `String` không-null và không chỉ chứa khoảng trắng. Quy tắc nằm trong **code của validator**, không tự sinh ra từ tên annotation.
7. `getDeclaredFields()` không hứa thứ tự trả về. Ví dụ sắp xếp field theo tên trước khi validate nên danh sách lỗi có thứ tự xác định: `age` rồi `username`.
8. Khi truyền object hợp lệ `Signup("Lan", 23)` và validator trả danh sách rỗng, chương trình mới gọi `register(valid)`. Chính nhánh điều khiển `if (errors.isEmpty())` quyết định cho phép thực hiện nghiệp vụ.

Logic tương đương đã được kiểm tra bằng Java 17 API trên JDK, cho đúng kết quả ở trên. Các field trong ví dụ là public để tập trung vào hành vi annotation; với private field, validator còn phải tuân thủ **Reflection access check** và ranh giới module.

## 4. Vì sao metadata không tự bảo vệ bất biến của object?

Annotation được gắn trên **phần tử khai báo**; nó không tự biến phép gán thành setter có điều kiện, không tự thay constructor, và không tự cài interceptor vào mọi lời gọi Java.

Ví dụ có thể tạo và thay đổi object ở nhiều đường:

~~~java
Signup user = new Signup("Lan", 23);
user.age = -1;                   // Field vẫn nhận giá trị -1.
user.username = "  ";           // Annotation không chặn phép gán.
~~~

Đây là đoạn minh họa sử dụng class `Signup` từ chương trình trên, không phải file độc lập. Bởi vì `Signup` khai báo field public và setter/constructor không kiểm tra, mọi caller có quyền Java đều có thể gán giá trị sai, dù annotation tồn tại.

Một validation engine chỉ có hiệu lực **tại những điểm được gọi**. Nếu bạn kiểm tra object trước khi lưu nhưng về sau object bị thay đổi hoặc một luồng code khác bỏ qua bước kiểm tra, dữ liệu xấu vẫn có thể đi qua. Validation ở **ranh giới tin cậy và điểm ghi dữ liệu** quan trọng hơn việc chỉ gắn annotation.

Trong thiết kế production, thường nên:

- Tạo bất biến trực tiếp trong constructor/factory, setter hoặc domain method khi đó là điều kiện luôn phải đúng.
- Gọi validation có chủ đích ở API boundary và trước tác vụ nhạy cảm (ghi database, chuyển tiền, cấp quyền, tạo tài nguyên...).
- Kết hợp ràng buộc cơ sở dữ liệu khi thích hợp, ví dụ `NOT NULL`, `CHECK` hoặc unique constraint. Annotation ở mã Java **không thay thế** những kiểm soát của database.
- Không giả định một đối tượng hợp lệ ở thời điểm kiểm tra sẽ mãi hợp lệ nếu sau đó cho phép mutation.

Điểm khác nhau về vai trò: **annotation biểu diễn chính sách; engine/logic mới thi hành chính sách**.

## 5. Java Reflection đọc annotation bằng API nào?

Một vài API tiêu biểu của `java.lang.reflect.AnnotatedElement` và `Field`:

| API | Công dụng | Có tự chạy validation không? |
| --- | --- | --- |
| `field.isAnnotationPresent(RequiredText.class)` | Hỏi annotation có hiện diện theo quy tắc Reflection không | Không |
| `field.getAnnotation(Minimum.class)` | Lấy annotation instance hoặc `null` | Không |
| `field.getAnnotations()` | Lấy annotation runtime hiện diện trên phần tử theo quy tắc API | Không |
| `field.getDeclaredAnnotations()` | Lấy annotation khai báo trực tiếp trên phần tử | Không |
| `clazz.getDeclaredFields()` | Liệt kê field khai báo trực tiếp trong class | Không |
| `minimum.value()` | Đọc giá trị cấu hình của annotation `@Minimum(...)` | Không |
| `field.get(bean)` / `field.getInt(bean)` | Đọc giá trị runtime của field | Không tự so sánh với annotation |

Annotation có các **element** như `int value();` — đây là thuộc tính cấu hình, không phải thân một hàm xử lý nghiệp vụ. Trong ví dụ `@Minimum(18)`, lời gọi `minimum.value()` đơn thuần trả `18`. Nếu code không thực hiện `if (age < 18)` hoặc tương đương, không có hành vi từ chối.

Lưu ý về inheritance: `@Inherited` chỉ liên quan đến một số quy tắc tìm annotation trên **class**, không có nghĩa annotation đặt trên field/method của superclass tự sao chép sang field/method ở subclass. Một annotation scanner phải quyết định có duyệt superclass, interface, method override hoặc nested object hay không; JVM không tự xây traversal cho nghiệp vụ của ứng dụng.

## 6. Compiler, annotation processor và runtime framework đóng vai trò gì?

### 6.1 Compiler nhận biết một số annotation chuẩn

Ví dụ:

~~~java
class Parent {
    void run() {}
}

class Child extends Parent {
    @Override
    void run() {}
}
~~~

Với `@Override`, compiler kiểm tra phương thức thật sự override/implement method phù hợp. Nếu sai, code có thể không biên dịch. Đó là hành vi của **compiler hiểu annotation chuẩn**; `@Override` không cung cấp một thân method được tự chạy ở runtime. `@Deprecated` cũng được công cụ dùng để cảnh báo các API không khuyến khích.

### 6.2 Annotation processor lúc compile time

Một annotation processor được đăng ký và kích hoạt có thể đọc annotation rồi kiểm tra mã, phát diagnostic hoặc tạo source/resource. Ví dụ framework có thể cung cấp processor cho `@GenerateBuilder`, nhưng việc **chỉ định nghĩa** `@GenerateBuilder` không tự tạo builder nếu không có processor/build pipeline xử lý nó.

Processor thường làm việc trên mô hình compiler (`javax.annotation.processing`, `javax.lang.model`), không phải bằng cách gọi method nghiệp vụ đang chạy. Retention `SOURCE` hoặc `CLASS` có thể đủ cho một số công cụ compile-time; không phải mọi annotation đều cần `RUNTIME`.

### 6.3 Runtime framework/container

Framework có thể đọc metadata lúc khởi tạo hoặc tại từng lời gọi và tổ chức:

- Validator cho các constraint annotations.
- Interceptor/proxy cho transaction, logging, metrics hoặc security.
- Bộ ánh xạ JSON/ORM để liên kết field/property với dữ liệu.
- Test runner tìm các method đánh dấu bằng test annotation rồi chủ động chạy.

Ví dụ `@Transactional` ở một framework cụ thể chỉ có ý nghĩa khi framework tạo và quản lý cơ chế transaction tương ứng. Nếu tự tạo instance bằng `new` ở ngoài container, gọi method từ một đường không đi qua proxy/interceptor, hoặc không cài/chạy framework cần thiết, hiệu ứng mong đợi có thể không xuất hiện. Hành vi chính xác phụ thuộc framework và cấu hình, không phải quy tắc tự chạy chung của Java annotations.

Không nên suy rằng một annotation có tên mang tính mệnh lệnh (như `@Validate`, `@Cacheable`, `@Secure`, `@Audit`) sẽ tự động thực hiện mệnh lệnh ấy.

## 7. Liên hệ với Bean Validation / Jakarta Validation

Trong hệ sinh thái Java, các annotation như `@NotNull`, `@NotBlank`, `@Size`, `@Min` thường gắn với **Jakarta Bean Validation**. Nhưng để các constraint có tác dụng phải có **validation provider/engine** và một điểm thực sự gọi hoặc tích hợp engine.

Quy trình khái niệm:

~~~text
Đối tượng có constraint annotations
           |
           v
Validation provider đọc metadata
           |
           v
Engine kiểm tra các giá trị hiện tại
           |
       +---+---+
       |       |
      hợp lệ   lỗi
       |       |
       v       v
tiếp tục     trả violations / báo lỗi
~~~

Nếu sử dụng Jakarta Validation trong ứng dụng, có thể gọi một `Validator` do provider cung cấp, ví dụ dưới đây là **mã minh họa cần Jakarta Validation API và provider tương ứng**, không phải chương trình Java SE chạy độc lập:

~~~java
// jakarta.validation.Validator validator = ...; // do provider cấp
// Set<ConstraintViolation<UserInput>> errors = validator.validate(input);
// if (!errors.isEmpty()) {
//     // Dừng/ báo lỗi có chủ đích.
// }
~~~

Trong Java SE thuần, không có quy tắc rằng tên annotation tự chế `@RequiredText` hoặc `@Minimum` tương đương constraint chuẩn của Jakarta. Ví dụ `AnnotationValidationDemo` ở mục 3 dùng **validator riêng**. Còn framework như Spring có thể tích hợp validation tại những điểm cụ thể (ví dụ xử lý request, method validation khi đã bật và cấu hình hợp lệ). Không được suy từ việc gắn annotation rằng mọi direct method call hoặc assignment trong toàn ứng dụng đều tự được kiểm tra.

Đặc biệt cần phân biệt:

- **Định nghĩa annotation constraint**: nêu điều kiện cần đạt.
- **Cài validator**: xác định thuật toán đánh giá.
- **Kích hoạt validation**: quyết định *khi nào*, *đối tượng nào*, *nhóm nào* được kiểm tra và *làm gì khi lỗi*.

Ba phần phải phối hợp mới tạo thành cơ chế validation thực sự.

## 8. Từ validation đến hành vi nghiệp vụ: annotation không thay người điều phối

Validation và nghiệp vụ không đồng nhất. Một annotation có thể mô tả điều kiện đầu vào, nhưng **kể cả dữ liệu hợp lệ**, hệ thống vẫn cần tự quyết định nghiệp vụ:

~~~java
List<String> errors = validate(signup);
if (!errors.isEmpty()) {
    throw new IllegalArgumentException(errors.toString());
}
register(signup);
~~~

Đây là đoạn minh họa dùng lại `validate`, `register` và `Signup` từ chương trình đầy đủ. Nếu bỏ nhánh `if` hoặc caller gọi thẳng `register`, logic nghiệp vụ vẫn có thể thực hiện trên dữ liệu không hợp lệ.

Một số câu hỏi phải do thiết kế ứng dụng/engine trả lời, annotation không tự quyết định:

1. Kiểm tra khi nhận HTTP request, trước khi ghi DB, trước khi gửi sự kiện, hay mọi thời điểm?
2. Trả lỗi thế nào: exception, HTTP 400/422, danh sách vi phạm, hay tích hợp UI?
3. Validation failure có rollback transaction, hủy event hoặc giữ audit log không?
4. Có cần kiểm tra cross-field (`startDate <= endDate`), quyền theo user, dữ liệu bên ngoài và trạng thái hiện hành không?
5. Nếu dữ liệu được tạo qua job, import, message queue hoặc Reflection thay vì HTTP, có phải gọi lại validator không?

Framework có thể cung cấp câu trả lời mặc định hoặc extension points, nhưng **câu trả lời đến từ framework và cấu hình**. Không phải thuộc tính tự nhiên của mọi annotation.

## 9. Các lỗi thường gặp

| Hiểu lầm / lỗi | Thực tế | Cách khắc phục |
| --- | --- | --- |
| “Đã đánh dấu `@RequiredText` thì constructor tự chặn null/blank.” | Annotation metadata không chặn phép gán/khởi tạo. | Gọi validator rõ ràng hoặc kiểm tra invariant trong constructor/factory. |
| “Có `@Retention(RUNTIME)` là validation tự chạy.” | `RUNTIME` chỉ giúp Reflection đọc annotation. | Viết/cấu hình component xử lý và một điểm gọi thích hợp. |
| “Đọc `getAnnotation(...)` sẽ làm rule có hiệu lực.” | `getAnnotation` chỉ trả metadata. | Đọc các element rồi thực thi kiểm tra và xử lý kết quả. |
| “`@Min(18)` tự chặn mọi phép gán vào field.” | Field vẫn có thể thay đổi nếu code có quyền gán. | Kiểm tra ở ranh giới ghi hoặc áp dụng invariant trong domain model. |
| “Cài thư viện annotations đủ rồi, không cần provider.” | Constraint cần engine và đường kích hoạt. | Kiểm tra dependency, provider, tích hợp framework và invocation path. |
| “`@Transactional` luôn hoạt động trong mọi direct call.” | Nhiều framework dùng proxy/interceptor và chỉ áp dụng ở đường gọi được quản lý. | Hiểu cơ chế intercept, cấu hình và lifecycle đối tượng. |
| “Annotation khai báo ở superclass chắc chắn được quét ở subclass.” | Quy tắc kế thừa annotation tùy loại phần tử/API và scanner. | Xem `@Inherited` đúng phạm vi, duyệt class hierarchy nếu cần. |
| “Validation đã chạy một lần thì object không thể sai nữa.” | Mutable object có thể thay đổi sau kiểm tra. | Thiết kế immutable/invariant và validate tại điểm tin cậy. |
| “Dữ liệu đã validate là được quyền xử lý nghiệp vụ.” | Hợp lệ kiểu dữ liệu không đồng nghĩa đủ thẩm quyền hay đáp ứng điều kiện business. | Tách input validation, authorization, business rules và transaction. |

### Lưu ý về Reflection access

Nếu validator quét private field, `Field.get(bean)` vẫn chịu kiểm tra truy cập Java. `getDeclaredFields()` có thể tìm được metadata, nhưng không bảo đảm caller được đọc field. `trySetAccessible()` có thể thất bại khi ranh giới named module không mở cho deep reflection. **Không** khắc phục lỗi quyền truy cập bằng cách bỏ validation một cách âm thầm; nên thiết kế public accessor/API hoặc điều chỉnh cấu hình module phù hợp, nếu có thẩm quyền.

### Lưu ý về nguồn tin cậy và bảo mật

Không dùng annotation và validator do ứng dụng tự gọi như **lớp bảo vệ duy nhất** cho permission, tiền bạc, số lượng tồn kho hoặc integrity. Hệ thống cần kiểm tra quyền, trạng thái giao dịch và các ràng buộc ở đúng nơi không thể bị bypass bởi các luồng vào khác. Annotation mô tả có thể là một phần kiến trúc đó, nhưng không có bảo đảm hệ thống sẽ tự thực thi chúng.

## 10. Checklist khi thiết kế annotation runtime

1. Xác định annotation dành cho compile-time, runtime hay tooling; nếu runtime Reflection cần đọc, chọn `@Retention(RUNTIME)`.
2. Xác định vị trí đặt với `@Target`: class, field, method, parameter, constructor, v.v.
3. Định nghĩa rõ ý nghĩa các element, giá trị mặc định, cách xử lý khi dữ liệu null/sai kiểu và thông báo lỗi.
4. Xây dựng hoặc chọn engine đọc metadata; nếu dùng custom annotation, phải có mã xử lý thực tế.
5. Chỉ rõ **điểm gọi**: constructor/factory, HTTP boundary, service method, transaction boundary, trước lưu DB, test runner, v.v.
6. Bảo đảm mọi đường vào cần thiết đều đi qua validation; không để direct call hoặc mutation quan trọng bypass.
7. Định nghĩa kết quả khi vi phạm (throw, return violations, reject/rollback, ghi log) và phân biệt với lỗi nghiệp vụ khác.
8. Kiểm thử cả trường hợp annotation **có mặt nhưng engine không chạy** và trường hợp engine chạy rồi từ chối đúng dữ liệu.
9. Kiểm tra Reflection access/module và class file cuối cùng trong môi trường triển khai.
10. Không trông chờ tên annotation, retention hay Reflection metadata tự tạo side effect.

## 11. Tự kiểm tra

**Câu 1:** `@Minimum(18)` có nghĩa JVM tự ném exception khi field `age` được đặt thành 16 không? **Không.** Chỉ có engine hoặc logic thực tế được gọi mới đánh giá và từ chối.

**Câu 2:** `field.isAnnotationPresent(Minimum.class)` trả `true`. Chứng minh validation đã chạy chưa? **Chưa.** Nó chỉ xác nhận có metadata runtime tương ứng.

**Câu 3:** `@Retention(RUNTIME)` khác `@Target(FIELD)` thế nào? **`Retention`** điều khiển mức lưu giữ annotation; **`Target`** điều khiển vị trí hợp lệ của annotation.

**Câu 4:** Tại sao trong chương trình ví dụ object tuổi 16 vẫn được “registered” ở lần gọi đầu? **Vì chương trình gọi nghiệp vụ trực tiếp trước khi gọi validator.** Không có cơ chế tự chạy validation do riêng annotation sinh ra.

**Câu 5:** Nếu dùng constraint của Jakarta Validation nhưng quên chạy/tích hợp provider thì điều gì xảy ra? **Annotation có thể vẫn tồn tại, nhưng không có bảo đảm constraint tự được đánh giá** trên mọi object hay mọi phép gán.

**Câu 6:** Annotation có thể tác động tới chương trình không? **Có, khi compiler, processor, framework hoặc chính ứng dụng được thiết kế để đọc và xử lý nó.** Không nên nhầm “không tự thực thi” với “không có tác dụng khi được công cụ tích hợp”.

**Ghi nhớ:** Annotation là **metadata về quy tắc hoặc ý định**. `@Retention(RUNTIME)` làm metadata có thể được Reflection quan sát; `getAnnotation` đọc metadata; **engine/caller** mới đánh giá validation, chặn dữ liệu và thực hiện hành vi nghiệp vụ.
