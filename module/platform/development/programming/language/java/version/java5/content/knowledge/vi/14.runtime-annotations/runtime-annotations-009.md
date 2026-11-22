# Xây dựng bảng đăng ký hành vi dựa trên annotation

## Từ metadata đến một hành vi có thể gọi

Annotation chỉ mô tả dữ liệu. Muốn gọi một hành vi từ thông tin đó, chương trình cần đọc annotation, kiểm tra phương thức phù hợp, lưu một ánh xạ rồi thực hiện lời gọi khi nhận được khóa.

Một bảng đăng ký (registry) là cấu trúc giữ ánh xạ **khóa hành vi → phương thức và đối tượng nhận lời gọi**. Ví dụ, khóa `"hello"` có thể trỏ tới phương thức `greet()` của một đối tượng đã được đăng ký. Khóa công bố không nhất thiết trùng tên phương thức Java.

Cách tổ chức này hữu ích khi có nhiều nhóm lệnh độc lập: nơi khai báo hành vi đặt khóa gần phương thức, còn bộ điều phối chỉ cần tra cứu bảng. Nhưng nếu chỉ có vài nhánh cố định, một `switch`, enum hoặc `Map<String, Supplier<String>>` được khai báo trực tiếp có thể rõ ràng hơn.

Bài dùng Java 17+, không cần framework. Các đối tượng được truyền rõ ràng khi dựng bảng; ví dụ không tự quét toàn bộ classpath.

## Chốt hợp đồng trước khi viết bộ quét

Registry trong bài có các quy tắc sau:

| Thành phần | Quy tắc |
| --- | --- |
| Annotation | `@Action` có retention `RUNTIME`, dùng trên phương thức |
| Nguồn quét | Chỉ phương thức được khai báo trực tiếp trên lớp thực của từng đối tượng được truyền vào |
| Chữ ký | Phương thức `public`, không `static`, không có tham số, trả về đúng `String`, truy cập được |
| Khóa | Khớp mẫu `[a-z][a-z0-9-]*`, phân biệt theo chính chuỗi đó |
| Trùng khóa | Từ chối ngay khi dựng bảng; không ghi đè âm thầm |
| Phương thức không có annotation | Bỏ qua |
| Gọi khóa không tồn tại | Báo lỗi rõ ràng |
| Sau khi dựng xong | Bảng ánh xạ không cho sửa thêm qua registry |

Việc kiểm tra chữ ký trước giúp lỗi cấu hình xuất hiện lúc khởi tạo, thay vì đến lần đầu người dùng gọi một lệnh. Khóa hợp lệ cũng giúp tránh những khác biệt khó nhìn thấy như khoảng trắng ở cuối.

## Ví dụ hoàn chỉnh

Lưu toàn bộ mã sau trong `ActionRegistryDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public final class ActionRegistryDemo {
    private ActionRegistryDemo() {
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Action {
        String value();
    }

    private record Binding(Object target, Method method) {
    }

    static final class Registry {
        private final Map<String, Binding> bindings;

        private Registry(Map<String, Binding> bindings) {
            this.bindings = Map.copyOf(bindings);
        }

        static Registry build(Object... targets) {
            Objects.requireNonNull(targets, "targets");
            Map<String, Binding> found = new HashMap<>();

            for (Object target : targets) {
                Objects.requireNonNull(target, "target");
                Method[] methods = target.getClass().getDeclaredMethods();
                Arrays.sort(methods, Comparator.comparing(Method::toGenericString));

                for (Method method : methods) {
                    if (method.isBridge() || method.isSynthetic()) {
                        continue;
                    }
                    Action action = method.getDeclaredAnnotation(Action.class);
                    if (action == null) {
                        continue;
                    }

                    int modifiers = method.getModifiers();
                    boolean valid = Modifier.isPublic(modifiers)
                            && !Modifier.isStatic(modifiers)
                            && method.getParameterCount() == 0
                            && method.getReturnType() == String.class
                            && method.canAccess(target);
                    if (!valid) {
                        throw new IllegalArgumentException(
                                "invalid handler: " + method.getName());
                    }

                    String key = action.value();
                    if (!key.matches("[a-z][a-z0-9-]*")) {
                        throw new IllegalArgumentException("invalid action key: " + key);
                    }
                    Binding previous = found.putIfAbsent(key, new Binding(target, method));
                    if (previous != null) {
                        throw new IllegalArgumentException("duplicate action: " + key);
                    }
                }
            }
            return new Registry(found);
        }

        String run(String key) {
            Objects.requireNonNull(key, "key");
            Binding binding = bindings.get(key);
            if (binding == null) {
                throw new IllegalArgumentException("unknown action: " + key);
            }
            try {
                return (String) binding.method().invoke(binding.target());
            } catch (IllegalAccessException ex) {
                throw new IllegalStateException("handler inaccessible: " + key, ex);
            } catch (InvocationTargetException ex) {
                throw new IllegalStateException("action failed: " + key, ex.getCause());
            }
        }
    }

    public static final class Commands {
        @Action("hello")
        public String greet() {
            return "Hello";
        }

        @Action("status")
        public String status() {
            return "READY";
        }

        @Action("fail")
        public String fail() {
            throw new IllegalStateException("boom");
        }
    }

    public static final class Duplicate {
        @Action("hello")
        public String anotherGreeting() {
            return "Other";
        }
    }

    public static final class BadSignature {
        @Action("bad")
        public String bad(String input) {
            return input;
        }
    }

    public static void main(String[] args) {
        Registry registry = Registry.build(new Commands());
        System.out.println(registry.run("hello"));
        System.out.println(registry.run("status"));

        try {
            registry.run("missing");
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }

        try {
            Registry.build(new Commands(), new Duplicate());
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }

        try {
            Registry.build(new BadSignature());
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }

        try {
            registry.run("fail");
        } catch (IllegalStateException ex) {
            System.out.println("handler cause: " + ex.getCause().getMessage());
        }
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp bằng JDK 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all -Werror ActionRegistryDemo.java
java ActionRegistryDemo
```

Stdout chính xác:

```text
Hello
READY
unknown action: missing
duplicate action: hello
invalid handler: bad
handler cause: boom
```

`BadSignature` và `Duplicate` là dữ liệu thử lỗi, không được đưa vào lần tạo registry thành công đầu tiên. Hai lần dựng bảng lỗi không làm thay đổi registry đã được tạo trước đó.

## Giai đoạn dựng bảng: khám phá, kiểm tra và chốt ánh xạ

### Đọc metadata đúng phạm vi

`@Retention(RUNTIME)` cho phép reflection đọc `Action`; `@Target(METHOD)` giới hạn vị trí sử dụng. Bộ quét lấy các phương thức bằng `getDeclaredMethods()` rồi đọc annotation trực tiếp trên từng `Method`.

`getDeclaredMethods()` không trả về các phương thức chỉ được thừa hưởng từ lớp cha, và thứ tự phần tử không được bảo đảm. Vì vậy bài chủ động chỉ nhận khai báo trực tiếp và sắp xếp trước khi kiểm tra để việc xử lý các phương thức trong một lớp có thứ tự xác định. Xem [`Class.getDeclaredMethods()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html#getDeclaredMethods()).

Các phương thức bridge hoặc synthetic do trình biên dịch tạo được bỏ qua theo chính sách của ví dụ. Nếu cần hỗ trợ kế thừa, interface hoặc lớp proxy của framework, phải định nghĩa thêm quy tắc tìm khai báo gốc và xử lý xung đột; đổi sang một API quét khác không tự giải quyết được các quyết định đó.

### Kiểm tra chữ ký trước khi lưu

Registry chỉ biết gọi phương thức không có tham số và diễn giải kết quả như `String`. Bởi vậy nó từ chối `bad(String input)` ngay lúc dựng bảng.

Kiểm tra `public`, không `static` và `canAccess(target)` bảo đảm phương thức phù hợp cách gọi của ví dụ. Các handler được khai báo trong lớp `public` của chương trình, không cần thay đổi quyền truy cập bằng reflection.

Nếu mở rộng sang phương thức nhận tham số, phải bổ sung hợp đồng ánh xạ dữ liệu đầu vào, kiểm tra kiểu và quy tắc chuyển đổi; không chỉ bỏ điều kiện `getParameterCount() == 0` rồi truyền dữ liệu tùy ý.

### Không để trùng khóa quyết định bởi thứ tự quét

Khóa lấy từ `action.value()`. Với `@Action("hello")` trên `greet()`, tên công bố là `hello`; đổi tên phương thức Java không bắt buộc đổi khóa nếu hợp đồng bên ngoài cần giữ nguyên.

`putIfAbsent` phát hiện một khóa đã được dùng. Ví dụ từ chối hai đối tượng cùng công bố `hello`, thay vì để một handler ghi đè handler khác. Điều này áp dụng cả khi vô tình đăng ký cùng một đối tượng hai lần.

`found` chỉ là dữ liệu tạm của một lần dựng bảng. Chỉ sau khi mọi kiểm tra thành công, registry mới giữ bản sao không cho sửa ánh xạ qua `Map.copyOf`. Xem [`Map.copyOf`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)).

## Giai đoạn gọi: tra cứu một lần, thực thi đúng đối tượng

`Binding` giữ cả `Method` và `target`. Cùng một lớp có thể có nhiều đối tượng với trạng thái khác nhau; biết tên phương thức mà không biết đối tượng nhận lời gọi chưa đủ cho phương thức instance.

`run("hello")` tìm `Binding` đã kiểm tra rồi gọi `Method.invoke(target)`. Vì chữ ký đã được kiểm tra trước, phép ép kết quả thành `String` phù hợp với hợp đồng; ví dụ cho phép handler trả `null`, vì `String` là kiểu tham chiếu và bài không đặt thêm quy tắc cấm giá trị đó.

Annotation không tự chạy `greet()`. Mã trong `build` đọc metadata, còn mã trong `run` thực hiện lời gọi. `Method.invoke` là cơ chế thực thi được lựa chọn trong ví dụ. Xem [`Method.invoke`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...)).

Không quét lại toàn bộ phương thức mỗi lần gọi. Mỗi lần dựng bảng làm việc khám phá và kiểm tra; các lần gọi sau chỉ tra cứu khóa rồi thực thi.

## Tách lỗi cấu hình, lỗi tra cứu và lỗi của hành vi

| Tình huống | Thời điểm phát hiện | Kết quả trong ví dụ |
| --- | --- | --- |
| Handler sai chữ ký | Dựng bảng | `invalid handler: bad` |
| Hai handler cùng khóa | Dựng bảng | `duplicate action: hello` |
| Không có khóa được yêu cầu | Tra cứu khi gọi | `unknown action: missing` |
| Handler được tìm thấy nhưng tự ném lỗi | Thực thi | Bọc lỗi và giữ nguyên nguyên nhân `boom` |

Khi phương thức đích ném ngoại lệ, reflection bọc nó trong `InvocationTargetException`. Bài lấy `getCause()` và giữ làm nguyên nhân của lỗi điều phối, giúp phân biệt lỗi trong handler với lỗi tra cứu. Xem [`InvocationTargetException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/InvocationTargetException.html).

Chính sách bọc nguyên nhân là lựa chọn minh họa. Một hệ thống lớn có thể cần phân loại lỗi nghiệp vụ, lỗi kỹ thuật và lỗi nghiêm trọng khác nhau; không nên bắt mọi lỗi rồi trả một chuỗi thành công rỗng.

## Giới hạn thiết kế cần giữ rõ

- Registry chỉ biết các đối tượng đã được truyền vào `build`. Một lớp có annotation nhưng chưa được đăng ký không tự xuất hiện trong bảng.
- Mỗi khóa trỏ tới một handler, không hỗ trợ quá tải dựa theo tham số hoặc tự chọn giữa nhiều ứng viên.
- Quy tắc bỏ qua phương thức kế thừa là chủ ý của bộ quét trong bài, không phải giới hạn bắt buộc của mọi registry.
- Bảng không cho sửa ánh xạ sau khi tạo, nhưng các đối tượng handler vẫn có thể mang trạng thái thay đổi được. Nếu gọi từ nhiều luồng, phải xem xét chính các đối tượng đó; `Map.copyOf` không tự khiến chúng an toàn luồng.
- Registry giữ tham chiếu tới đối tượng handler trong suốt vòng đời của nó. Các tài nguyên hoặc vòng đời đối tượng cần do thành phần sở hữu chúng quản lý.

Với dự án cần thêm nhiều chức năng, hãy giữ riêng ba trách nhiệm: khám phá metadata, kiểm tra và dựng bảng, thực thi hành vi. Không biến annotation thành nơi chứa cả thuật toán hay tự tạo một hệ thống quét/lắp ráp đối tượng phức tạp khi chưa có nhu cầu.

## Thực hành có kết quả đối chiếu

1. Thêm `@Action("version")` lên một phương thức `public String version()` trả về `"1.0"` trong `Commands`. Dựng lại bảng rồi gọi `run("version")`; kết quả là `1.0`.
2. Đổi khóa của phương thức đó thành `" status "`. Dựng bảng phải thất bại vì khóa không khớp mẫu; ví dụ không tự cắt khoảng trắng để che lỗi cấu hình.
3. Đổi phương thức thành `public static String version()`. Nó phải bị từ chối lúc dựng bảng, trước khi có lời gọi thực thi.
4. Đăng ký `new Commands()` hai lần trong cùng một lần `build`. Registry phải báo trùng khóa thay vì chọn một đối tượng tùy ý.
5. Tạo lớp con không khai báo lại phương thức nào của `Commands` bằng một bản sao thử nghiệm đã bỏ `final` ở lớp cha. Bộ quét hiện tại chỉ khảo sát lớp thực của đối tượng, nên không đăng ký các phương thức chỉ được thừa hưởng.

Để tự đánh giá thiết kế, hãy giải thích được vì sao annotation cần `RUNTIME`, vì sao bảng phải giữ đối tượng nhận lời gọi, vì sao khóa trùng bị từ chối và vì sao ngoại lệ của handler cần giữ lại nguyên nhân.