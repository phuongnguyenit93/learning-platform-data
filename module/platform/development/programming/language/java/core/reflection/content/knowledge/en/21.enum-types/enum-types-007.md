# Đọc method và field do compiler bổ sung mà không phụ thuộc tên nội bộ

## 1. Reflection nhìn thấy lớp đã biên dịch

Mã nguồn một enum có thể rất ngắn, nhưng lớp sau khi biên dịch chứa thêm thành viên để thực hiện quy tắc của Java và hỗ trợ JVM. Vì vậy, danh sách trả về từ `getDeclaredFields()` hoặc `getDeclaredMethods()` không phải bản chép nguyên văn những gì lập trình viên đã gõ trong tệp nguồn.

Khi xây công cụ đọc cấu trúc enum, cần phân biệt ba nhóm:

1. **Thành viên được khai báo tường minh:** field và method do người viết mã khai báo.
2. **Thành viên được ngôn ngữ khai báo ngầm định:** chẳng hạn các field biểu diễn hằng enum và hai method `values()`, `valueOf(String)`.
3. **Thành viên hỗ trợ do trình biên dịch tạo:** có thể gồm field lưu dữ liệu nội bộ, method trợ giúp và phương thức cầu nối (`bridge method`).

Không phải mọi thành viên do compiler bổ sung đều được nhận diện bằng `isSynthetic()`. Đặc biệt, các API ngầm định của enum có vị trí riêng trong hợp đồng ngôn ngữ.

Mục tiêu của bài là đọc và phân loại metadata đúng. Việc gọi method, đọc giá trị field hoặc thay đổi dữ liệu bên trong enum là các thao tác khác.

## 2. Điều gì được Java bảo đảm, điều gì thuộc cách biên dịch?

Với enum `E`, Java quy định:

- Mỗi hằng enum tương ứng với một field `public static final` mang tên hằng và có kiểu `E`.
- Có method `public static E[] values()`.
- Có method `public static E valueOf(String name)`.

Đây là những thành viên có hợp đồng ngôn ngữ. Dùng tên `values` hoặc `valueOf` kèm đúng tham số để tìm API tương ứng không phải là phụ thuộc một tên nội bộ tùy ý.

Ngược lại, cách trình biên dịch lưu mảng hằng hay tách các bước khởi tạo có thể khác nhau. Những tên như `$VALUES` hoặc `$values` có thể xuất hiện khi khảo sát đầu ra của một trình biên dịch, nhưng không phải API công khai mà ứng dụng nên tìm để lấy danh sách hằng.

Không viết thuật toán kiểu “tìm một field có đúng tên nội bộ ấy rồi đọc nó”. Cũng không suy ra vai trò chỉ từ hình dạng tên như bắt đầu bằng `$`, viết hoa hoặc chứa từ `values`.

| Nhu cầu | Điểm dựa phù hợp |
| --- | --- |
| Nhận diện field biểu diễn hằng enum | `Field.isEnumConstant()` |
| Nhận biết field/method được đánh dấu synthetic | `isSynthetic()` trên thành viên |
| Nhận biết method cầu nối | `Method.isBridge()` |
| Nhận diện API ngầm định của enum | Lớp khai báo, tên API, tham số, kiểu trả về và modifier |
| Lấy các đối tượng hằng theo thứ tự khai báo | `Class.getEnumConstants()` |
| Tìm toàn bộ phần triển khai để chẩn đoán bytecode | Giữ metadata và ghi rõ vai trò, không loại bỏ mặc định |

Các cờ metadata trả lời câu hỏi kỹ thuật. Chính sách hiển thị của công cụ phải quyết định nhóm nào được đưa vào tài liệu hoặc màn hình kiểm tra.

## 3. Ví dụ: phân loại field và method của một enum

Lưu thành `EnumCompilerMembersDemo.java`:

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.stream.Collectors;

public class EnumCompilerMembersDemo {
    enum TaskState {
        WAITING(10),
        RUNNING(20);

        private final int code;
        public static final TaskState DEFAULT = WAITING;
        public static final String VERSION = "v1";

        TaskState(int code) {
            this.code = code;
        }

        public int code() {
            return code;
        }
    }

    private static String methodLabel(Method method) {
        String parameters = Arrays.stream(method.getParameterTypes())
                .map(Class::getSimpleName)
                .collect(Collectors.joining(","));
        return method.getName() + "(" + parameters + ")->"
                + method.getReturnType().getSimpleName();
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<TaskState> type = TaskState.class;

        String constantFields = Arrays.stream(type.getDeclaredFields())
                .filter(Field::isEnumConstant)
                .map(Field::getName)
                .sorted()
                .collect(Collectors.joining(","));

        String otherFields = Arrays.stream(type.getDeclaredFields())
                .filter(field -> !field.isEnumConstant())
                .filter(field -> !field.isSynthetic())
                .map(Field::getName)
                .sorted()
                .collect(Collectors.joining(","));

        String methods = Arrays.stream(type.getDeclaredMethods())
                .filter(method -> !method.isSynthetic())
                .filter(method -> !method.isBridge())
                .map(EnumCompilerMembersDemo::methodLabel)
                .sorted()
                .collect(Collectors.joining("; "));

        System.out.println("constantFields=" + constantFields);
        System.out.println("otherFields=" + otherFields);
        System.out.println("methods=" + methods);
        System.out.println("DEFAULT.enumConstant="
                + type.getDeclaredField("DEFAULT").isEnumConstant());
        System.out.println("values.synthetic="
                + type.getDeclaredMethod("values").isSynthetic());
        System.out.println("valueOf.synthetic="
                + type.getDeclaredMethod("valueOf", String.class)
                      .isSynthetic());
        System.out.println("declarationOrder="
                + Arrays.toString(type.getEnumConstants()));
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 EnumCompilerMembersDemo.java
java EnumCompilerMembersDemo
~~~

Kết quả với `javac` của JDK 17:

~~~text
constantFields=RUNNING,WAITING
otherFields=DEFAULT,VERSION,code
methods=code()->int; valueOf(String)->TaskState; values()->TaskState[]
DEFAULT.enumConstant=false
values.synthetic=false
valueOf.synthetic=false
declarationOrder=[WAITING, RUNNING]
~~~

Ví dụ đã chủ động sắp xếp tên field và nhãn method để kết quả in ổn định. Không dựa vào thứ tự mảng metadata do Reflection trả về.

Cần phân biệt **thứ tự hiển thị đã sắp xếp** với **thứ tự hằng trong khai báo**. Danh sách field được sắp theo tên nên có `RUNNING` trước `WAITING`; `getEnumConstants()` vẫn giữ `WAITING` trước `RUNNING`.

Hằng `DEFAULT` là một field do tác giả khai báo, dù nó cũng là `public static final` và có kiểu `TaskState`. `isEnumConstant()` vẫn trả `false`. Vì vậy, chỉ kiểm tra kiểu field và modifier không đủ để nhận diện hằng enum.

Hai method `values()` và `valueOf(String)` xuất hiện dù tác giả không viết phần khai báo của chúng. Trong đầu ra được kiểm tra ở đây, chúng không mang cờ synthetic. Lọc hết thành viên synthetic vẫn giữ lại hai API này.

Chương trình không in tên hoặc số lượng thành viên hỗ trợ nội bộ. Khi đổi compiler hoặc cách biên dịch, chi tiết hỗ trợ có thể đổi mà không làm thay đổi mục đích của phần phân loại.

## 4. isSynthetic không đồng nghĩa với “không do tác giả viết”

`Field.isSynthetic()` và `Method.isSynthetic()` đọc dấu hiệu synthetic của thành viên. Dấu hiệu này hữu ích để nhận diện phần hỗ trợ kỹ thuật, nhưng không tái tạo đầy đủ lịch sử tác giả của mã nguồn.

Có hai chiều cần tránh suy diễn:

- Một thành viên được compiler bổ sung có thể tương ứng với khai báo ngầm định của Java, như các API enum vừa thấy.
- Một thành viên synthetic vẫn có thể quan trọng đối với một công cụ phân tích lớp đã biên dịch, dù không phù hợp để hiển thị như API nghiệp vụ.

Vì vậy, hãy đặt tên chính sách chính xác. Bộ lọc `!method.isSynthetic()` có nghĩa là “bỏ method được đánh dấu synthetic”, không có nghĩa là “chỉ giữ method được viết tường minh trong nguồn”.

Nếu cần xác định chính xác đoạn nào được tác giả viết trong một tệp nguồn, chỉ metadata Reflection không phải một bản đồ nguồn đầy đủ. Có thể cần đọc nguồn hoặc metadata bổ sung phục vụ mục tiêu đó. Đừng gán nhãn “do người dùng viết” cho mọi method không synthetic mà chưa xét thành viên ngầm định.

Tương tự, không mặc định ẩn mọi field `static` hoặc mọi field có kiểu mảng để loại dữ liệu hỗ trợ: enum hoàn toàn có thể khai báo field ứng dụng thuộc các dạng ấy.

## 5. Nếu muốn ẩn API ngầm định, phải kiểm tra đúng hợp đồng

Một công cụ tài liệu có thể muốn giữ API enum chuẩn; công cụ khác chỉ muốn liệt kê phần mở rộng do tác giả định nghĩa. Đó là quyết định hiển thị, cần được tách khỏi cơ chế đọc metadata.

Nếu chính sách yêu cầu ẩn `values()` và `valueOf(String)`, đừng loại mọi method chỉ vì tên là `values` hoặc `valueOf`. Enum có thể có một overload hợp lệ như `valueOf(int)` do tác giả viết.

Lưu thành `EnumApiFilterDemo.java`:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.stream.Collectors;

public class EnumApiFilterDemo {
    enum Tier {
        BASIC, PREMIUM;

        public static Tier valueOf(int code) {
            return switch (code) {
                case 1 -> BASIC;
                case 2 -> PREMIUM;
                default -> throw new IllegalArgumentException("Unknown code");
            };
        }
    }

    static boolean isImplicitEnumApi(Class<?> enumType, Method method) {
        if (!enumType.isEnum()
                || method.getDeclaringClass() != enumType) {
            return false;
        }

        int modifiers = method.getModifiers();
        if (!Modifier.isPublic(modifiers)
                || !Modifier.isStatic(modifiers)) {
            return false;
        }

        if (method.getName().equals("values")) {
            return method.getParameterCount() == 0
                    && method.getReturnType().isArray()
                    && method.getReturnType().getComponentType() == enumType;
        }

        if (method.getName().equals("valueOf")) {
            return method.getParameterCount() == 1
                    && method.getParameterTypes()[0] == String.class
                    && method.getReturnType() == enumType;
        }

        return false;
    }

    private static String methodLabel(Method method) {
        return method.getName() + "("
                + Arrays.stream(method.getParameterTypes())
                      .map(Class::getSimpleName)
                      .collect(Collectors.joining(","))
                + ")";
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<Tier> type = Tier.class;

        Method values = type.getDeclaredMethod("values");
        Method textLookup = type.getDeclaredMethod("valueOf", String.class);
        Method numericLookup = type.getDeclaredMethod("valueOf", int.class);

        System.out.println("values(): implicit="
                + isImplicitEnumApi(type, values));
        System.out.println("valueOf(String): implicit="
                + isImplicitEnumApi(type, textLookup));
        System.out.println("valueOf(int): implicit="
                + isImplicitEnumApi(type, numericLookup));

        String kept = Arrays.stream(type.getDeclaredMethods())
                .filter(method -> !method.isSynthetic())
                .filter(method -> !method.isBridge())
                .filter(method -> !isImplicitEnumApi(type, method))
                .map(EnumApiFilterDemo::methodLabel)
                .sorted()
                .collect(Collectors.joining("; "));
        System.out.println("kept=" + kept);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 EnumApiFilterDemo.java
java EnumApiFilterDemo
~~~

Kết quả:

~~~text
values(): implicit=true
valueOf(String): implicit=true
valueOf(int): implicit=false
kept=valueOf(int)
~~~

Hàm nhận diện dùng đối tượng `Class` để kiểm tra kiểu trả về và kiểu tham số, không so sánh các chuỗi tên kiểu đã rút gọn. Các tên đơn giản trong `methodLabel` chỉ phục vụ bản in của ví dụ.

Việc lọc theo hợp đồng này áp dụng cho một lớp enum Java hợp lệ. Nó không phải bộ nhận diện mọi thành viên do mọi bộ sinh bytecode có thể tạo ra.

Các kiểm tra về modifier và lớp khai báo còn giúp tránh nhầm một method cùng tên nhưng khác vai trò. Chính sách ẩn chỉ loại hai API đã xác định; overload `valueOf(int)` vẫn được giữ.

## 6. Bridge method: cùng tên và tham số vẫn có thể thấy hai method

Enum cũng có thể triển khai interface generic. Khi cần nối hợp đồng sau xóa kiểu với phần thực hiện có kiểu cụ thể hơn, trình biên dịch có thể tạo bridge method.

Đây không phải một API enum mới. Nó là phần hỗ trợ để lời gọi qua kiểu interface vẫn đến đúng phần thực hiện.

Lưu thành `EnumBridgeMetadataDemo.java`:

~~~java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;

public class EnumBridgeMetadataDemo {
    interface CodeSupplier<T> {
        T code();
    }

    enum Signal implements CodeSupplier<String> {
        ON;

        @Override
        public String code() {
            return "on";
        }
    }

    public static void main(String[] args) {
        Arrays.stream(Signal.class.getDeclaredMethods())
                .filter(method -> method.getName().equals("code"))
                .sorted(Comparator.comparing(
                        method -> method.getReturnType().getName()))
                .forEach(method -> System.out.println(
                        method.getName() + " -> "
                        + method.getReturnType().getSimpleName()
                        + " synthetic=" + method.isSynthetic()
                        + " bridge=" + method.isBridge()));
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 EnumBridgeMetadataDemo.java
java EnumBridgeMetadataDemo
~~~

Kết quả với `javac` của JDK 17:

~~~text
code -> Object synthetic=true bridge=true
code -> String synthetic=false bridge=false
~~~

Tác giả chỉ viết một method `String code()`. Method trả `Object` là bridge được compiler tạo để phục vụ hợp đồng của `CodeSupplier<T>` sau xóa kiểu.

Nếu công cụ tài liệu hiển thị cả hai như hai thao tác nghiệp vụ riêng biệt, người dùng có thể thấy API bị lặp. Một chính sách tài liệu thông thường có thể loại method bridge. Một công cụ chẩn đoán bytecode nên giữ nó và ghi rõ cờ tương ứng.

Không ghép hoặc loại method chỉ theo tên. Ở mức Reflection/JVM, có thể quan sát các method trùng tên và kiểu tham số nhưng khác kiểu trả về, như ví dụ này. Khi tạo khóa metadata, cần giữ thông tin lớp khai báo, tên, tham số và kiểu trả về phù hợp với mục tiêu của công cụ.

`isBridge()` trả lời vai trò cầu nối cụ thể. `isSynthetic()` trả lời dấu hiệu synthetic rộng hơn. Bridge method là một trường hợp synthetic; không phải mọi method synthetic đều là bridge.

## 7. Chọn đúng phạm vi đọc trước khi lọc

`getDeclaredFields()` và `getDeclaredMethods()` lấy thành viên được khai báo trực tiếp trong lớp đang xét, bao gồm cả thành viên không public. Chúng không tự gộp mọi thành viên kế thừa.

Điều này giải thích vì sao `values()` và `valueOf(String)` có trong metadata trực tiếp của enum, còn các method như `name()` và `ordinal()` đến từ lớp cơ sở `Enum`.

Nếu mục tiêu là API public gồm phần kế thừa, `getMethods()` có phạm vi khác. Hãy xác định phạm vi trước, rồi mới áp dụng chính sách synthetic/bridge/enum API. Nếu không, công cụ có thể “thiếu” hoặc “thừa” method vì chọn sai phạm vi từ đầu.

Khi bắt đầu từ một đối tượng hằng enum có thân riêng, lớp thực tế của hằng còn có thể là lớp con ẩn danh. Nếu muốn khảo sát lớp enum chung, chuẩn hóa bằng `constant.getDeclaringClass()`; nếu muốn khảo sát phần riêng của hằng, dùng lớp thực tế của nó.

Không dùng thứ tự mảng field/method từ Reflection làm thứ tự nguồn. Sắp xếp bản trình bày khi cần đầu ra ổn định; lấy danh sách hằng qua API enum khi cần thứ tự khai báo của các hằng.

## 8. Quan sát metadata không đòi hỏi đọc dữ liệu nội bộ

Các ví dụ dùng tên, kiểu, modifier và cờ thành viên để phân loại. Không cần gọi `setAccessible(true)` hoặc đọc field private để biết một field có phải enum constant hay synthetic hay không.

Nếu chỉ cần các giá trị hằng, dùng `getEnumConstants()`. Nếu đã biết kiểu enum trong nguồn, dùng `values()`. Cả hai giúp mã tránh phụ thuộc cách compiler cất dữ liệu hỗ trợ.

Đọc một field nội bộ không tạo thêm một hợp đồng ổn định cho ứng dụng. Thay đổi mảng lưu trữ hỗ trợ, nếu tìm thấy và truy cập được, còn có thể phá giả định của enum hoặc của thư viện khác. Khả năng nhìn thấy metadata không phải lý do để sửa trạng thái ấy.

Cũng cần giữ ranh giới thực thi: lấy `Method` chỉ mô tả method; gọi `invoke` mới thực hiện lời gọi. Đọc giá trị field tĩnh hoặc lấy các đối tượng hằng có thể liên quan đến khởi tạo lớp. Một trình xem metadata không nên gọi thử method chỉ để quyết định thành viên thuộc nhóm nào.

## 9. Lỗi thường gặp và cách kiểm tra

| Sai lầm | Điều cần kiểm tra lại |
| --- | --- |
| Tìm field có tên nội bộ cố định để lấy các hằng | Dùng API enum thay vì dữ liệu hỗ trợ |
| Nhận diện hằng chỉ bằng public/static/final và kiểu field | Dùng `Field.isEnumConstant()`; một field bí danh có thể cùng kiểu và modifier |
| Coi mọi method không synthetic là method tác giả viết | Xét các API được khai báo ngầm định |
| Loại mọi method tên `valueOf` | Kiểm tra tham số, kiểu trả về, modifier và lớp khai báo |
| Hiển thị bridge như một thao tác nghiệp vụ thứ hai | Quyết định chính sách `isBridge()` theo mục đích |
| Loại synthetic ngay khi đọc rồi không lưu dấu vết | Công cụ chẩn đoán có thể cần chính những thành viên ấy |
| So sánh ảnh chụp metadata theo thứ tự JVM trả về | Sắp xếp khóa/nhãn trước khi so sánh |
| Dùng số lượng field/method nội bộ như một cam kết | Chỉ kiểm tra hợp đồng cần thiết, không đóng cứng chi tiết compiler |
| Gọi API đọc giá trị private chỉ để phân loại | Dùng metadata công khai và các cờ vai trò |

Một cách tổ chức rõ ràng là: thu thập metadata, phân loại vai trò, rồi chọn chính sách trình bày. Như vậy, một bộ đọc có thể phục vụ cả màn hình API lẫn chế độ chẩn đoán mà không phải đoán vai trò từ tên thành viên.

## 10. Tự kiểm tra

1. Vì sao bộ lọc `!method.isSynthetic()` vẫn có thể giữ `values()` và `valueOf(String)`?
2. Một field `public static final MyEnum DEFAULT` có chắc là hằng enum không?
3. Nếu enum khai báo thêm `valueOf(int)`, có nên loại nó chỉ vì tên method là `valueOf`?
4. Trong ví dụ generic, tại sao thấy cả `Object code()` và `String code()`?
5. Muốn danh sách hằng theo thứ tự nguồn, nên sắp xếp field hay dùng API nào?
6. Có nên ghi cứng tên hoặc số lượng field lưu trữ nội bộ trong một bài kiểm tra tính đúng của ứng dụng không?

Đáp án:

1. Chúng là API được Java khai báo ngầm định; không thể đồng nhất “compiler bổ sung” với “synthetic”.
2. Không. Dùng `Field.isEnumConstant()` để phân biệt field hằng enum với field thông thường.
3. Không. Đó có thể là overload do tác giả viết; phải xét đúng hợp đồng cần lọc.
4. Compiler tạo bridge để nối hợp đồng generic sau xóa kiểu với phần thực hiện trả `String`.
5. Dùng `Class.getEnumConstants()` hoặc `values()` khi biết kiểu cụ thể.
6. Không. Kiểm tra hành vi/hợp đồng cần thiết và tránh phụ thuộc các chi tiết hỗ trợ có thể thay đổi.

## Tài liệu đối chiếu

- [JLS 17 — Các thành viên ngầm định của enum](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9.3).
- [JLS 17 — Dạng nhị phân, synthetic và khai báo ngầm định](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html#jls-13.1).
- [Java 17 — Field.isEnumConstant và isSynthetic](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html#isEnumConstant()).
- [Java 17 — Method.isBridge và isSynthetic](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#isBridge()).
