# Lọc `static`, `synthetic`, `bridge` và thành viên không phù hợp khi thiết kế công cụ Reflection

## 1. Vì sao một công cụ Reflection cần lọc thành viên?

Một class có thể chứa hằng `static`, field do compiler sinh, bridge method phục vụ generic dispatch, method `Object`, hoặc API quản trị mà công cụ không được công bố. `getDeclaredMethods()` và `getDeclaredFields()` liệt kê ứng viên theo phạm vi truy vấn; chúng **không áp dụng hợp đồng nghiệp vụ**.

Bộ hiển thị hành vi của instance có thể bỏ `static` và `bridge`; trình phân tích bytecode lại cần giữ chính những member ấy. Vì vậy lọc dựa trên **vai trò đọc/ghi/gọi**, chữ ký, visibility, annotation và nguồn khai báo, với quyết định rõ khi gặp `synthetic`. Ví dụ Java 17+ trong bài minh họa cả hai bộ lọc: method hiển thị và field có thể ghi.

## 2. Đọc đúng metadata trước khi lọc

`Class<?>` trả các nhóm thành viên sau:

| API | Phạm vi | Điểm cần chú ý |
| --- | --- | --- |
| `getDeclaredMethods()` | Method khai báo trực tiếp trong class/interface, mọi visibility | Không tự lấy method kế thừa; có thể thấy bridge/synthetic |
| `getMethods()` | Method `public` của kiểu và các method `public` được kế thừa | Có thể bao gồm method `Object`; không chỉ method do kiểu khai báo |
| `getDeclaredFields()` | Field khai báo trực tiếp, mọi visibility | Có thể bao gồm field do compiler sinh |
| `getFields()` | Field `public` của kiểu và field `public` được kế thừa | Field có thể bị che khuất, nên xem declaring class |
| `getDeclaredConstructors()` | Constructor khai báo trực tiếp, mọi visibility | Constructor không kế thừa |
| `getConstructors()` | Constructor `public` của chính kiểu | Không có “constructor kế thừa” |

**Không có thứ tự trả về được bảo đảm** từ các mảng Reflection nói trên. Không dùng vị trí `methods[0]` hoặc `fields[0]` làm ý nghĩa nghiệp vụ; nếu cần đầu ra ổn định, tự sắp xếp theo khóa rõ ràng.

Một metadata member có thể trả:

- `member.getName()`: tên.
- `member.getDeclaringClass()`: class/interface khai báo trực tiếp member.
- `member.getModifiers()`: tập cờ modifier, giải mã bằng `java.lang.reflect.Modifier`.
- `member.isSynthetic()`: member được đánh dấu synthetic trong class file.
- Với `Method`: `isBridge()`, `isVarArgs()`, `getParameterTypes()`, `getReturnType()`, `getAnnotations()`.
- Với `Field`: `getType()`, `getGenericType()` và `isEnumConstant()`.
- Với `Constructor<?>`: `getParameterTypes()`, `isVarArgs()` và `isSynthetic()`.

Tên và modifier **không đủ** để quyết định có thể truy cập hoặc gọi: phải xét declaring class, package, module, receiver và quy tắc access tại nơi gọi.

## 3. Lọc `static` chính xác

`static` có ý nghĩa khác nhau với field và method:

- **Static method** thuộc về class, không đòi instance receiver.
- **Static field** thuộc về class, không đòi instance receiver; có thể là hằng, biến cấu hình hoặc dữ liệu dùng chung.
- **Instance method/field** làm việc trên một đối tượng nhận lời gọi.

Kiểm tra bằng `Modifier.isStatic(member.getModifiers())`:

```java
boolean instanceMethod = !Modifier.isStatic(method.getModifiers());
boolean instanceField = !Modifier.isStatic(field.getModifiers());
```

Đây là đoạn minh họa; `method`, `field` và import `java.lang.reflect.Modifier` phải có trong ngữ cảnh.

Bộ ánh xạ trạng thái của *một đối tượng* thường bỏ static field. Công cụ liệt kê hàm tiện ích lại có thể **chỉ** chọn static method. Không áp bộ lọc “loại static” cho mọi công cụ một cách máy móc.

**Lưu ý:** Class lồng khai báo `static` không có nghĩa constructor của nó là “static constructor”. Constructor không phải method static; lọc `Modifier.isStatic` trên method/field khác với quyết định loại constructor.

## 4. `synthetic` là gì?

`Member.isSynthetic()` cho biết member được đánh dấu **`ACC_SYNTHETIC`** trong metadata class file (theo cách JVM/Reflection biểu diễn). Compiler có thể tạo những member này để hiện thực các chi tiết ngôn ngữ như truy cập nội bộ, capture, bridge hoặc dạng hỗ trợ khác.

Ví dụ có thể gặp:

- Field tổng hợp chứa tham chiếu tới enclosing instance trong một số inner class.
- Field compiler tạo để chứa giá trị bắt từ ngữ cảnh xung quanh.
- Method trợ giúp compiler sinh ra.
- Bridge method được tạo để bảo toàn đa hình khi có generic erasure hoặc covariant return.

**Không dựa vào tên bắt đầu bằng `$`** để nhận biết synthetic: `$` là ký tự hợp lệ trong identifier Java, và quy ước tên compiler thay đổi theo trình biên dịch/phiên bản. Đồng thời, **không phải mọi member compiler tạo đều `isSynthetic() == true`**: chẳng hạn một accessor hợp lệ của record hoặc constructor mặc định có thể là API nguồn của kiểu.

`isSynthetic()` phù hợp để loại member kỹ thuật ra khỏi giao diện nghiệp vụ, nhưng với công cụ phân tích bytecode hoặc debugger thì chính member synthetic lại là dữ liệu cần quan sát.

## 5. `bridge` xuất hiện vì sao, khác `synthetic` ra sao?

**Bridge method** là phương thức do compiler có thể tạo để bảo toàn quy tắc override/dispatch của Java khi chữ ký bytecode chịu ảnh hưởng của type erasure hoặc covariant return type.

Ví dụ nguồn:

```java
class Parent<T> {
    public T convert(T input) {
        return input;
    }
}

class Child extends Parent<String> {
    @Override
    public String convert(String input) {
        return input.toUpperCase();
    }
}
```

Ở bytecode, `Parent<T>.convert(T)` sử dụng dạng đã erasure tương ứng `convert(Object)`. `Child.convert(String)` có chữ ký khác tại mức JVM, nên compiler có thể sinh method bridge `convert(Object)` trong `Child` để chuyển kiểu đầu vào và gọi `convert(String)` thật.

Trong Reflection:

- `Method.isBridge()` nhận biết method bridge.
- `Method.isSynthetic()` thường cũng `true` trên bridge do `javac` tạo, nhưng **hai khái niệm không đồng nhất**. Đánh giá hai cờ riêng nếu chính sách cần.
- Nếu công cụ hiển thị cả method triển khai và bridge như hai operation nghiệp vụ, người dùng có thể thấy trùng lặp hoặc hai chữ ký khó hiểu.
- **Không xóa hoặc “vô hiệu hóa” bridge khi chạy chương trình.** Bridge là thành phần hợp lệ của hành vi đa hình Java. “Lọc” ở đây chỉ là quyết định *có đưa vào catalog API của công cụ hay không*.

Một bộ liệt kê method hướng tới lập trình viên thường lọc:

```java
!method.isBridge() && !method.isSynthetic()
```

Nhưng đây vẫn là chính sách của công cụ. Công cụ phân tích tương thích binary, debugger hoặc bytecode inspector có thể phải giữ cả hai.

## 6. Ví dụ Java 17+ hoàn chỉnh: lọc method và field theo mục tiêu

Ví dụ thiết kế hai danh sách:

1. **Method hiển thị:** chỉ method `public`, thuộc instance, được khai báo trực tiếp trong class, không synthetic/bridge, không tham số, có giá trị trả về.
2. **Field có thể ghi qua giao diện dữ liệu:** chỉ field `public`, thuộc instance, không synthetic, không `final`.

Lưu thành **`MemberFilterDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class MemberFilterDemo {
    public static class Parent<T> {
        public T convert(T value) {
            return value;
        }
    }

    public static class Sample extends Parent<String> {
        public String label = "initial";
        public final String id = "fixed";
        public static String category = "demo";
        private String secret = "hidden";

        public static String version() {
            return "v1";
        }

        public String describe() {
            return "sample";
        }

        public void reset() {
            label = "";
        }

        @Override
        public String convert(String value) {
            return value.toUpperCase(Locale.ROOT);
        }

        private String internal() {
            return secret;
        }
    }

    public static void main(String[] args) {
        Method[] declaredMethods = Sample.class.getDeclaredMethods();
        Field[] declaredFields = Sample.class.getDeclaredFields();

        List<String> visibleMethods = Arrays.stream(declaredMethods)
                .filter(m -> Modifier.isPublic(m.getModifiers()))
                .filter(m -> !Modifier.isStatic(m.getModifiers()))
                .filter(m -> !m.isSynthetic() && !m.isBridge())
                .filter(m -> m.getParameterCount() == 0)
                .filter(m -> m.getReturnType() != void.class)
                .map(Method::getName)
                .sorted()
                .toList();

        List<String> writableFields = Arrays.stream(declaredFields)
                .filter(f -> Modifier.isPublic(f.getModifiers()))
                .filter(f -> !Modifier.isStatic(f.getModifiers()))
                .filter(f -> !Modifier.isFinal(f.getModifiers()))
                .filter(f -> !f.isSynthetic())
                .map(Field::getName)
                .sorted()
                .toList();

        long bridgeCount = Arrays.stream(declaredMethods)
                .filter(Method::isBridge)
                .count();

        System.out.println("methods=" + visibleMethods);
        System.out.println("writableFields=" + writableFields);
        System.out.println("bridges=" + bridgeCount);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac MemberFilterDemo.java
java MemberFilterDemo
```

Kết quả khi biên dịch bằng `javac` của JDK 17:

```text
methods=[describe]
writableFields=[label]
bridges=1
```

**Vì sao kết quả này đúng?**

- `describe()` được chọn: method `public`, instance, không tham số, trả `String` và không phải bridge/synthetic.
- `version()` bị loại vì `static`; `reset()` bị loại vì trả `void`; `convert(String)` bị loại bởi chính sách method không tham số; `internal()` bị loại vì `private`.
- Khi override `Parent<String>.convert(String)`, `javac` tạo một bridge kiểu `convert(Object)` trong `Sample`. Bộ lọc phát hiện bridge/synthetic và không đưa method này vào danh sách nghiệp vụ.
- `label` được chọn vì là field `public`, instance, không `final`.
- `category` bị loại vì `static`; `id` bị loại vì `final`; `secret` bị loại vì `private`.
- `sorted()` làm kết quả đầu ra ổn định ngay cả khi `getDeclaredMethods()`/`getDeclaredFields()` không bảo đảm thứ tự.

**Giới hạn của ví dụ:** Đây là chính sách tạo một danh sách hiển thị và một danh sách field có thể ghi, **không phải** bộ lọc đúng cho mọi serializer, ORM, test framework hoặc API generator. Ví dụ dùng `getDeclared...` nên chỉ xét member khai báo trực tiếp trong `Sample`, không đưa inherited method `Object` vào kết quả. Nó kiểm tra modifier nhưng **chưa thực hiện kiểm tra quyền truy cập khi gọi trên module khác**: điều đó phải được giải quyết riêng khi tích hợp công cụ thực.

## 7. Định nghĩa “không phù hợp” theo vai trò, chữ ký và visibility

Bên cạnh `static`, `synthetic` và `bridge`, công cụ thường phải kiểm tra thêm:

| Tiêu chí | Khi nào cần lọc? | Điều không được suy diễn |
| --- | --- | --- |
| `public` / `protected` / package-private / `private` | Khi chỉ công bố public API hoặc muốn giới hạn truy cập | Có modifier `public` chưa đảm bảo gọi được qua mọi module |
| `abstract` | Nếu công cụ đòi thao tác tự có implementation trong class | Method abstract vẫn có thể được dispatch trên instance subclass cụ thể |
| `final` trên field | Nếu công cụ muốn *ghi* field | Field `final` vẫn có thể đọc; không đồng nghĩa synthetic |
| `transient` trên field | Khi serialization policy chọn bỏ transient | Không tự động vô nghĩa với mọi framework |
| `volatile` trên field | Khi cần quy tắc truy cập đồng bộ thích hợp | `volatile` không đồng nghĩa field phải loại khỏi mọi danh sách |
| `isVarArgs()` | Nếu bộ gọi không biết dựng mảng varargs | Varargs vẫn là Java method hợp lệ |
| Danh sách tham số và kiểu trả về | Khi tool chỉ hỗ trợ một hình dạng API nhất định | Không suy ra method sai nếu chữ ký không khớp chính sách |
| Annotation | Khi muốn chỉ công bố member được đánh dấu | Annotation chỉ đọc được ở runtime khi retention phù hợp |
| Declaring class và kế thừa | Khi chỉ liệt kê API của class đang xét | Inherited/default methods có thể là API cần giữ |
| Khả năng truy cập thực tế | Trước khi gọi method, constructor hoặc đọc/ghi field | Metadata tìm được chưa đồng nghĩa được phép sử dụng |
| Cặp tên và chữ ký overload | Khi xây operation registry | Chỉ dùng tên method làm key có thể gây ghi đè overload |

Ví dụ trường `transient` có ý nghĩa với Java serialization truyền thống nhưng một thư viện ánh xạ dữ liệu có thể có hợp đồng riêng. Một method `void reset()` là API hợp lệ; nó chỉ bị loại nếu **công cụ đang xây danh sách hàm đọc có kết quả** như ví dụ trên.

Nếu dùng danh sách method để tự động gọi, cần xác định rõ loại tham số có thể cấp được: `Class<?>[] getParameterTypes()`, `getReturnType()`, `getExceptionTypes()`, `isVarArgs()` và annotation của method/parameter. Không nên gọi ngẫu nhiên mọi method không tham số vì chúng có thể gây tác dụng phụ, ghi file, gửi request hoặc làm thay đổi state.

## 8. Chú ý khi duyệt kế thừa, overload và method của `Object`

`getDeclaredMethods()` chỉ xét những method khai báo trực tiếp. `getMethods()` xét public method theo phạm vi đã nói và có thể trả các method quen thuộc như `toString()`, `hashCode()` hoặc `getClass()` khi phù hợp.

Nếu chỉ muốn operation nghiệp vụ, có thể sử dụng chính sách công khai theo annotation thay vì tự suy luận từ tên. Khi cho phép method inherited:

1. Xác định rõ có chấp nhận method thừa kế từ superclass hay interface mặc định (`default method`) không.
2. Dùng `getDeclaringClass()` để biết nơi khai báo; đừng mặc định mọi `Method` trả về từ `Child.class.getMethods()` đều thuộc `Child`.
3. Tránh coi mọi method cùng tên là trùng: `process(int)` và `process(String)` là **hai overload**.
4. Khi tạo khóa operation, nên chứa tên và **danh sách kiểu tham số**; nếu tích hợp JVM signature/covariant return/bridge thì xác định chính sách biểu diễn đầy đủ.
5. Có thể cần giải quyết method override theo quy tắc “triển khai phù hợp nhất” nếu làm catalog tổng hợp của hierarchy. Không lấy method đầu tiên được trả về để làm lựa chọn mặc định.

Ví dụ minh họa key phân biệt overload:

```java
static String signature(Method method) {
    String params = Arrays.stream(method.getParameterTypes())
            .map(Class::getTypeName)
            .collect(java.util.stream.Collectors.joining(", "));
    return method.getName() + "(" + params + ")";
}
```

Đoạn này phải đặt trong class có import `java.lang.reflect.Method` và `java.util.Arrays`; nó không phải chương trình độc lập. Trong hệ thống nhiều class, nên bổ sung identity của declaring class/loader/module cho những mục đích cần phân biệt thực thể. Với dữ liệu ổn định để so sánh, đừng chỉ dựa vào `Method.toString()` hoặc thứ tự tự nhiên của API Reflection.

**Ví dụ đặc thù:** Record có accessor hợp lệ như `name()`; enum có các trường hằng enum và method do ngôn ngữ cung cấp; những thứ ấy có thể không mang cờ synthetic. Nếu một tool không muốn công bố chúng, phải có quy tắc theo **loại class/role/annotation** riêng, chứ không suy ra từ `isSynthetic()`.

## 9. Annotation whitelist và chính sách tường minh

Với một tool thực hiện hành động thực tế, cách an toàn hơn việc tự động gọi mọi public method có thể là yêu cầu annotation định danh operation được hỗ trợ. Annotation cần `@Retention(RetentionPolicy.RUNTIME)` để đọc bằng Reflection tại runtime.

Ví dụ định hướng:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface ToolAction {}

class ExampleActions {
    @ToolAction
    public String status() {
        return "OK";
    }

    public void deleteAll() {
        // Không tự động công bố vì thiếu @ToolAction.
    }
}
```

Đây là snippet minh họa, không có `main`. Khi duyệt `Method`, có thể thêm `method.isAnnotationPresent(ToolAction.class)` để chỉ nhận operation được chủ ý khai báo. Một hệ thống thật còn phải xác thực quyền của người dùng, giới hạn tham số, xử lý lỗi và side effect; annotation **không tự cung cấp quyền truy cập hay bảo mật**.

Cần quyết định trước về annotation kế thừa/override. `@Inherited` chỉ có quy tắc kế thừa đối với annotation trên **class**; không mặc nhiên khiến annotation trên method của superclass được kế thừa theo ý muốn của framework. Nếu cần quy tắc riêng cho method bị override, phải duyệt hierarchy và định nghĩa logic đó công khai.

## 10. Trường hợp constructor và nested class

Constructor không dùng `Method.isBridge()`; có thể kiểm tra `Constructor.isSynthetic()`, visibility, annotation và danh sách tham số. Constructor không kế thừa, vì vậy `getDeclaredConstructors()` và `getConstructors()` có semantics khác hẳn các phương thức.

Ví dụ công cụ dependency injection thường chọn một constructor có annotation thích hợp hoặc theo một quy ước xác định. Không mặc định chọn **constructor đầu tiên** trong mảng; thứ tự Reflection không ổn định. Không tự động gọi mọi constructor tìm được: constructor có thể làm công việc tốn kém, tạo tài nguyên hoặc có side effect.

Đối với nested class, cần phân biệt:

- Nested class `static` thường không cần enclosing instance để tạo instance.
- Non-static inner class thường có tham chiếu tới enclosing instance và constructor ở bytecode có thể mang tham số bổ sung liên quan tới enclosing instance.
- Compiler có thể tạo field synthetic hỗ trợ mối liên hệ đó.

Do đó, công cụ tự dựng constructor arguments cần quan sát **parameter types thực tế**, không suy từ hình thức mã nguồn và cũng không bỏ mọi tham số synthetic theo giả định cứng.

## 11. Quyền truy cập: “đủ điều kiện hiển thị” chưa phải “gọi được”

Trước khi gọi `Method.invoke(...)`, `Constructor.newInstance(...)` hoặc `Field.get/set(...)`, phải xét quyền của caller và module. Lớp `public` ở package không exported cho module gọi vẫn có thể không truy cập được theo cách kỳ vọng. `getDeclaredMethod` tìm private member không tự làm private member thành public.

Các điểm thực hành:

- `method.canAccess(receiver)`, `field.canAccess(receiver)` hoặc `constructor.canAccess(null)` có thể hỗ trợ kiểm tra truy cập ở ngữ cảnh thích hợp; instance member cần receiver phù hợp, static member dùng `null`.
- Không lạm dụng `setAccessible(true)` để vượt bảo vệ; Java Platform Module System (JPMS) có thể từ chối deep reflection, ví dụ ném `InaccessibleObjectException`. `opens` và `exports` có mục đích khác nhau.
- Nếu chuyển sang `MethodHandle` hoặc `VarHandle`, các thao tác `MethodHandles.Lookup` vẫn mang mô hình quyền riêng; việc đã có `Method` không bảo đảm `unreflect` sẽ thành công.
- Khi registry cache metadata/handle theo class, cân nhắc vòng đời class loader: cache toàn cục có thể giữ class của plugin không được giải phóng.

Bộ lọc metadata có thể xác định *ứng viên*. Trước khi thực hiện, công cụ phải xác thực capability của thao tác thực tế và chính sách quyền truy cập trong bối cảnh người dùng/chương trình.

## 12. Kiểm tra chất lượng bộ lọc trong hệ thống thật

Một bộ lọc đáng tin cậy phải có những kiểm tra sau:

- **Generic bridge:** một override do erasure tạo bridge không xuất hiện hai lần trong danh sách nghiệp vụ, nhưng cơ chế dispatch Java vẫn hoạt động.
- **Static:** field/method static được chọn hay loại theo chính sách đã công bố.
- **Synthetic:** những member compiler sinh không lọt vào catalog nghiệp vụ nếu chính sách cấm, và một member không synthetic cũng không mặc nhiên được chấp nhận.
- **Final, private, transient, varargs:** được xét riêng theo mục tiêu đọc, ghi, gọi hay serialize.
- **Overload:** `f(int)` và `f(String)` có danh tính khác nhau.
- **Inheritance/default method:** không bị bỏ hoặc nhân đôi ngoài chủ đích.
- **Enum/record/nested class:** được kiểm tra với loại class cụ thể, không chỉ với tên field/method.
- **Module/class loader:** cùng tên kiểu nhưng do loader khác định nghĩa không bị coi là một class duy nhất; lỗi quyền được xử lý minh bạch.
- **Determinism:** kết quả được sắp xếp bằng comparator/key nhất quán, không phụ thuộc thứ tự Reflection.
- **Side effects:** chỉ gọi thành viên mà hợp đồng và quyền đã cho phép; công cụ liệt kê metadata không cần thử chạy mọi method.

Một thiết kế tốt nên tách ba bước **thu thập metadata → quyết định hợp lệ → thực thi hoặc công bố**. Nhờ đó có thể kiểm tra predicate lọc độc lập, giải thích vì sao một member bị bỏ và thay đổi chính sách theo từng tác vụ mà không làm biến đổi hành vi của Java runtime.

### Câu hỏi tự kiểm tra

1. Vì sao `getDeclaredMethods()` có thể trả nhiều method hơn số method viết trực tiếp trong source của subclass?
2. `Method.isBridge()` dùng để phát hiện điều gì? Nếu bridge là synthetic, có nên bỏ kiểm tra bridge trong mọi công cụ không?
3. Với một bộ serialize object, khi nào `Modifier.isStatic` là tiêu chí hợp lý? Khi nào là tiêu chí sai?
4. Vì sao field `final` có thể được đọc nhưng thường không nên nằm trong danh sách có thể ghi?
5. Vì sao dùng mỗi tên method làm khóa registry có thể làm mất overload?
6. `getMethods()` và `getDeclaredMethods()` khác nhau thế nào về inherited member và visibility?
7. Nếu `Method` là public nhưng package đích không exported cho module gọi, có thể bỏ bước kiểm tra truy cập không?
8. Vì sao annotation whitelist cần `RetentionPolicy.RUNTIME`, và vì sao annotation vẫn chưa đủ để bảo đảm một lời gọi an toàn?

**Ghi nhớ:** `static`, `synthetic` và `bridge` là những đặc điểm kỹ thuật có ý nghĩa riêng. Công cụ Reflection nên lọc chúng theo **hợp đồng sử dụng cụ thể**, kết hợp với visibility, chữ ký, quyền truy cập, kế thừa, annotation và khả năng thực thi; không coi bất kỳ một cờ nào là tiêu chí chất lượng duy nhất.
