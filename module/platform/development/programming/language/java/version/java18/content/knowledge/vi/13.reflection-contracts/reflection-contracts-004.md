# Tra cứu method overload bằng kiểu tham số chính xác thay vì kiểu runtime của giá trị đối số

## 1. Mục tiêu: xác định chữ ký trước khi tra cứu reflection

Trong module **JAVA_VERSION_JAVA18**, chủ đề **Hợp đồng reflection** tập trung vào cách kiểm chứng những hợp đồng Java vẫn áp dụng trên JDK hiện đại. Java 18 không thay đổi nguyên tắc cốt lõi này: khi dùng `Class.getMethod(String, Class<?>...)` hay `Class.getDeclaredMethod(String, Class<?>...)`, Java **tra cứu theo tên phương thức và danh sách kiểu tham số khai báo chính xác**, không tự chạy lại thuật toán chọn overload của compiler dựa trên giá trị đối số.

Giả sử một API công khai có:

```java
public String describe(Number value);
public String describe(Object value);
```

Giá trị `Integer.valueOf(42)` có kiểu runtime là `Integer.class`; nó có thể được truyền vào một tham số `Number` hoặc `Object`. Nhưng cả hai overload ở trên **đều không có tham số khai báo `Integer`**:

```java
Class<?> runtimeType = Integer.valueOf(42).getClass(); // Integer.class
// getMethod("describe", runtimeType) -> NoSuchMethodException
```

Đó không phải lỗi của `Integer` hay reflection. Lỗi xuất phát từ việc dùng **kiểu runtime của giá trị** thay cho **kiểu tham số trong chữ ký API**.

Sau bài này, bạn sẽ:

1. Chọn chính xác một overload qua `Class<?>` của từng tham số khai báo.
2. Phân biệt `getMethod` và `getDeclaredMethod`, tra cứu và gọi phương thức.
3. Xử lý đúng subtype/interface, primitive và wrapper, `null`, mảng/varargs.
4. Nhận diện tác động của generic type erasure, bridge method và quyền truy cập.
5. Viết các test chứng minh lựa chọn overload là **cố định**, có thể lặp lại trên JDK hiện đại.

## 2. Hai cơ chế khác nhau: compiler chọn overload, reflection tra cứu chữ ký

### 2.1. Overload ở lời gọi Java thông thường

Khi viết:

```java
Number number = Integer.valueOf(42);
service.describe(number);
```

Compiler dùng **kiểu tĩnh** của biểu thức `number` là `Number` để chọn overload `describe(Number)`. Nếu thay bằng biến kiểu tĩnh `Integer` và có overload `describe(Integer)`, compiler có thể chọn overload cụ thể hơn. Đây là quá trình xác định overload lúc biên dịch theo quy tắc ngôn ngữ Java (kể cả các chuyển đổi được phép và varargs).

Sau khi chọn chữ ký, **overriding** của instance method vẫn có thể dispatch đến implementation ở subclass lúc chạy. Overloading và overriding là hai cơ chế khác nhau: một bên chọn chữ ký; bên kia chọn phần triển khai của chữ ký đã chọn.

### 2.2. Reflection không tự chọn overload bằng đối số

Với reflection, bạn chỉ rõ chữ ký cần lấy:

```java
Method selected = Service.class.getMethod("describe", Number.class);
Object result = selected.invoke(service, Integer.valueOf(42));
```

Phần `getMethod` chỉ so khớp chữ ký (`describe(Number)`). Phần `invoke` chỉ gọi `selected` với giá trị `Integer`, vì `Integer` là subtype của `Number` nên có thể truyền vào tham số `Number`.

**Không có bước nào** trong `invoke` gọi lại `getMethod` hoặc tự chọn overload `describe(Integer)`, `describe(Object)`, v.v. Một lời gọi reflection có thể đưa đối số tương thích với nhiều overload, nhưng `Method` đại diện cho **chính xác một chữ ký đã tra cứu**.

### 2.3. Bảng so sánh nhanh

| Hành động | Dựa trên dữ liệu nào? | Có tự chọn overload gần nhất không? |
| --- | --- | --- |
| Lời gọi `service.describe(value)` trong mã Java | Kiểu tĩnh và quy tắc overload của compiler | Có, tại compile time |
| `type.getMethod("describe", Number.class)` | Tên và đúng `Class<?>` của tham số khai báo | Không |
| `type.getDeclaredMethod("describe", Number.class)` | Cùng chữ ký, nhưng chỉ trong lớp đang xét | Không |
| `method.invoke(receiver, value)` | `Method` đã chọn và khả năng truyền đối số | Không |
| `value.getClass()` | Kiểu runtime của object không-null | Không phải chữ ký mà API công bố |

Quy tắc thực hành: **tra cứu bằng hợp đồng khai báo; gọi bằng giá trị**.

## 3. `getMethod` và `getDeclaredMethod` khác nhau ở phạm vi

### 3.1. `getMethod(String, Class<?>...)`

`getMethod` tìm **phương thức public** với tên và danh sách kiểu tham số chính xác, tính cả public method được kế thừa từ superclass hoặc interface. Nếu không có chữ ký phù hợp, ném `NoSuchMethodException`.

```java
Method m = Example.class.getMethod(
        "process", CharSequence.class, int.class);
```

Hai `Class<?>` sau tên phương thức là **kiểu tham số khai báo theo đúng thứ tự**; không phải kiểu của các object mà bạn định gửi trong `invoke`.

### 3.2. `getDeclaredMethod(String, Class<?>...)`

`getDeclaredMethod` chỉ tìm phương thức **được khai báo trong đúng lớp này**, kể cả `private`, `protected`, package-private và `public`, nhưng **không tìm phương thức chỉ được kế thừa**.

```java
Method internal = Example.class.getDeclaredMethod(
        "internal", String.class);
```

Tìm thấy method không có nghĩa được phép gọi nó. Việc `Method.invoke` thành công còn phụ thuộc kiểm tra quyền truy cập, quan hệ module và receiver thích hợp. Với các JDK hiện đại, strong encapsulation của module khiến `setAccessible(true)` không phải một lối đi phổ quát để gọi private method của mọi module.

### 3.3. Tham số trả về không nằm trong danh sách tra cứu

`getMethod` không nhận tham số mô tả return type; hãy lấy phương thức bằng tên + parameter types rồi kiểm tra `getReturnType()` nếu hợp đồng cần xác minh kết quả. Có thể xuất hiện bridge method hoặc trường hợp covariant return từ compiler; đừng dùng một giá trị return giả lập làm “đối số” cho `getMethod`.

## 4. Các ca dễ nhầm: subtype, interface, primitive, null và varargs

### 4.1. Kiểu runtime subtype không thay thế kiểu tham số cha

```java
public String process(Number value) { return "number"; }

Number value = Integer.valueOf(7);

// Đúng: chữ ký có Number.
Method found = Target.class.getMethod("process", Number.class);

// Sai: Target không công bố process(Integer).
Target.class.getMethod("process", value.getClass());
```

Ở bước gọi, `found.invoke(target, value)` vẫn hợp lệ vì `Integer` có thể được gán cho `Number`. Lookup và invocation phải được đánh giá riêng.

### 4.2. Interface càng cho thấy `getClass()` không phải chữ ký

```java
public String render(CharSequence value) {
    return value.toString();
}

String text = "xin chào";

// Đúng: method được khai báo bằng interface CharSequence.
Method m = Target.class.getMethod("render", CharSequence.class);
String result = (String) m.invoke(target, text);

// Sai: text.getClass() là String.class, không phải CharSequence.class.
Target.class.getMethod("render", text.getClass());
```

Tình huống này đặc biệt thường gặp với `List`, `Map`, `Runnable`, proxy hoặc implementation được tạo bởi framework: kiểu triển khai có thể thay đổi, nhưng chữ ký interface của API vẫn ổn định.

### 4.3. Primitive `int.class` không phải wrapper `Integer.class`

```java
public String count(int n) { return "count=" + n; }

// Đúng khi tra cứu:
Method m = Target.class.getMethod("count", int.class);

// Sai dù đối số thực tế sau này là Integer.
Target.class.getMethod("count", Integer.class);

// Đúng khi gọi: Method.invoke có thể unbox Integer thành int.
String result = (String) m.invoke(target, Integer.valueOf(5));
```

`int.class` và `Integer.class` là hai đối tượng `Class` khác nhau. **Autoboxing/unboxing có thể tham gia ở bước gọi**, nhưng không khiến `getMethod("count", Integer.class)` tìm được chữ ký `count(int)`.

Ở `Method.invoke`, các phép chuyển đổi hợp lệ gồm unboxing và widening primitive trong phạm vi được reflection hỗ trợ; không có phép ép hẹp tùy tiện hay chuyển String sang số chỉ vì nội dung có dạng số.

### 4.4. `null` không có kiểu runtime để gọi `getClass()`

```java
Object value = null;

// value.getClass() ném NullPointerException.
// Hãy chọn chữ ký cụ thể từ hợp đồng:
Method m = Target.class.getMethod("render", CharSequence.class);
Object result = m.invoke(target, new Object[] { null });
```

Nếu API có `process(String)` và `process(Object)`, một giá trị `null` có thể phù hợp với cả hai. Reflection không suy luận overload “tốt nhất” từ `null`; chính caller phải chọn `String.class` hoặc `Object.class`.

Cẩn trọng: `Method.invoke` là phương thức varargs. `new Object[] { null }` thể hiện rõ rằng bạn đang truyền **một đối số có giá trị null**, thay vì một mảng đối số `null` hoặc không truyền đối số nào.

### 4.5. Varargs trong khai báo là tham số mảng của chữ ký

```java
public String join(String prefix, String... parts) {
    return prefix + ":" + String.join("|", parts);
}

// Chữ ký phản chiếu là (String, String[]), không phải (String, String).
Method m = Target.class.getMethod(
        "join", String.class, String[].class);

Object result = m.invoke(target,
        new Object[] { "P", new String[] { "a", "b" } });
```

`Method.invoke` không chạy lại phép biến đổi varargs của lời gọi Java thông thường để gom `"a"` và `"b"` thành `String[]` cho phương thức đích. Hãy chủ động tạo mảng ở đúng vị trí tham số khai báo; mảng `Object[]` ngoài cùng là danh sách các đối số cho `Method.invoke`.

### 4.6. Thứ tự và số lượng tham số là một phần của chữ ký

`getMethod("put", String.class, Integer.class)` khác `getMethod("put", Integer.class, String.class)`. Chữ ký có hai tham số không giống chữ ký một tham số ngay cả khi giá trị ở runtime có thể được gói trong một array/list. Reflection **không tự đổi thứ tự, thêm tham số mặc định hoặc chuyển đổi object tuỳ ý**.

## 5. Chương trình kiểm chứng overload bằng chữ ký chính xác

Lưu ví dụ thành `ExactOverloadLookupDemo.java` và chạy trên JDK 18+. Chương trình cố ý chứa các phép tìm **không có method tương ứng** để chứng minh lookup không làm overload resolution dựa vào đối số runtime.

```java
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.List;

public final class ExactOverloadLookupDemo {
    public static final class Target {
        public String process(Number value) {
            return "NUMBER:" + value;
        }
        public String process(Object value) {
            return "OBJECT:" + value;
        }
        public String render(CharSequence value) {
            return value == null ? "TEXT:null" : "TEXT:" + value;
        }
        public String count(int value) {
            return "COUNT:" + value;
        }
        public String widen(long value) {
            return "LONG:" + value;
        }
        public String join(String prefix, String... parts) {
            return prefix + ":" + String.join("|", parts);
        }
        public String accept(List<String> values) {
            return "LIST:" + values.size();
        }
        public String choose(String value) {
            return "STRING";
        }
        public String choose(Object value) {
            return "OBJECT";
        }
        private String secret(String text) {
            return "SECRET:" + text;
        }
    }

    public static void main(String[] args) throws Exception {
        Target receiver = new Target();
        Class<?> type = Target.class;

        // Integer có thể truyền cho Number/Object; không có overload Integer.
        Integer value = Integer.valueOf(42);
        expectMissing(type, "process", value.getClass());
        Method number = type.getMethod("process", Number.class);
        Method object = type.getMethod("process", Object.class);
        assertResult("NUMBER:42", number.invoke(receiver, value));
        assertResult("OBJECT:42", object.invoke(receiver, value));

        // String là implementation của interface CharSequence.
        String text = "hello";
        expectMissing(type, "render", text.getClass());
        Method render = type.getMethod("render", CharSequence.class);
        assertResult("TEXT:hello", render.invoke(receiver, text));

        // Tra cứu primitive, còn invoke có thể unbox và widen.
        expectMissing(type, "count", Integer.class);
        Method count = type.getMethod("count", int.class);
        assertResult("COUNT:5", count.invoke(receiver, Integer.valueOf(5)));
        Method widen = type.getMethod("widen", long.class);
        assertResult("LONG:5", widen.invoke(receiver, Integer.valueOf(5)));

        // Null không có runtime type: caller chọn chữ ký.
        Method chooseString = type.getMethod("choose", String.class);
        Method chooseObject = type.getMethod("choose", Object.class);
        assertResult("STRING",
                chooseString.invoke(receiver, new Object[] { null }));
        assertResult("OBJECT",
                chooseObject.invoke(receiver, new Object[] { null }));

        // Chữ ký varargs vẫn có một tham số mảng String[].
        Method join = type.getMethod("join", String.class, String[].class);
        if (!join.isVarArgs()) {
            throw new AssertionError("Expected varargs method");
        }
        expectMissing(type, "join", String.class, String.class);
        assertResult("P:a|b", join.invoke(receiver,
                new Object[] { "P", new String[] { "a", "b" } }));

        // List<String> bị erasure thành List.class trong chữ ký.
        List<String> values = List.of("a", "b");
        expectMissing(type, "accept", values.getClass());
        Method accept = type.getMethod("accept", List.class);
        assertResult("LIST:2", accept.invoke(receiver, values));

        // getDeclaredMethod thấy private; getMethod chỉ tìm public.
        Method secret = type.getDeclaredMethod("secret", String.class);
        if (!Modifier.isPrivate(secret.getModifiers())) {
            throw new AssertionError("Unexpected access modifier");
        }
        expectMissing(type, "secret", String.class);

        System.out.println("EXACT_SIGNATURE_TESTS=PASS");
    }

    private static void expectMissing(
            Class<?> type, String name, Class<?>... params) throws Exception {
        try {
            type.getMethod(name, params);
            throw new AssertionError("Unexpected method: "
                    + name + Arrays.toString(params));
        } catch (NoSuchMethodException expected) {
            System.out.println("EXPECTED_NO_SUCH_METHOD=" + name);
        }
    }

    private static void assertResult(String expected, Object actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    "Expected " + expected + " but got " + actual);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ExactOverloadLookupDemo.java
java ExactOverloadLookupDemo
```

Kết quả cuối phải chứa `EXACT_SIGNATURE_TESTS=PASS`. Các dòng `EXPECTED_NO_SUCH_METHOD=...` là phép thử **âm tính thành công**: nếu `getMethod` tự suy ra `process(Number)` từ `Integer.class` hay `render(CharSequence)` từ `String.class`, phép thử sẽ thất bại.

Chương trình không dùng `setAccessible(true)` để gọi method private. Nó chỉ cho thấy `getDeclaredMethod` và `getMethod` có phạm vi tìm kiếm khác nhau.

### 5.1. Vì sao cùng Integer nhưng gọi được hai overload?

```java
Method asNumber = Target.class.getMethod("process", Number.class);
Method asObject = Target.class.getMethod("process", Object.class);

asNumber.invoke(receiver, Integer.valueOf(42)); // process(Number)
asObject.invoke(receiver, Integer.valueOf(42)); // process(Object)
```

Cùng một đối số runtime có thể gọi hai implementation khác nhau vì **Method được chọn trước**. Nếu mục tiêu là mô phỏng overload resolution của compiler, bạn phải tự xây thuật toán xét convertibility, specificity, varargs, ambiguity và trường hợp `null`. Đừng tự làm việc này nếu hợp đồng API đã công bố rõ chữ ký.

### 5.2. Method public được kế thừa

```java
class Parent {
    public String show(CharSequence text) {
        return "parent:" + text;
    }
}
class Child extends Parent {}

// Đúng: getMethod tìm public inherited method.
Method inherited = Child.class.getMethod("show", CharSequence.class);

// Không thấy method chưa được Child tự khai báo.
Child.class.getDeclaredMethod("show", CharSequence.class); // lỗi lookup
```

Với kết quả đầu, `inherited.getDeclaringClass()` là `Parent.class`. Đây là một khác biệt riêng giữa phạm vi của `getMethod` và `getDeclaredMethod`, không liên quan đến kiểu runtime của đối số truyền vào.

## 6. Kiểu generic, erasure và bridge method

### 6.1. Generic parameter không tạo `List<String>.class`

```java
public void save(List<String> entries) { /* ... */ }

// Chữ ký runtime sau erasure chứa java.util.List.
Method m = Service.class.getMethod("save", List.class);

Class<?>[] erased = m.getParameterTypes();
java.lang.reflect.Type[] generic = m.getGenericParameterTypes();
```

`getParameterTypes()` trả `Class<?>[]` đại diện cho kiểu sau erasure (`List.class`). `getGenericParameterTypes()` có thể cho biết `List<String>` từ thông tin khai báo, nhưng `getMethod` vẫn nhận `List.class`. Trong Java, hai overload chỉ khác `List<String>` và `List<Integer>` không được khai báo cùng lớp vì có cùng erasure.

`values.getClass()` đối với `List.of(...)` thường là một class implementation nội bộ, không phải `List.class`, vì vậy không thể dùng thay chữ ký `save(List)`.

### 6.2. Bridge method do compiler sinh

Với generic interface hoặc covariant return, compiler có thể sinh bridge method để giữ tương thích bytecode:

```java
interface Converter<T> {
    T convert(T input);
}
final class StringConverter implements Converter<String> {
    @Override
    public String convert(String input) {
        return input.trim();
    }
}
```

Khi duyệt `getDeclaredMethods()`, bạn có thể gặp `convert(String)` cùng một method bridge `convert(Object)`. Kiểm tra `method.isBridge()` và `method.isSynthetic()` nếu đang xây danh sách phương thức nghiệp vụ:

```java
for (Method method : StringConverter.class.getDeclaredMethods()) {
    if (method.isBridge() || method.isSynthetic()) continue;
    // Chỉ xét các method của API chủ ý công bố.
}
```

Không nên suy rằng method bridge được sinh ra chính là overload nghiệp vụ được khai báo trong mã nguồn. Lookup theo `Object.class` đôi khi tìm thấy bridge, nhưng đó không thay thế cho việc chọn chữ ký API dự kiến.

### 6.3. Class loader cũng là một phần của danh tính kiểu

Hai class có cùng tên đầy đủ nhưng được định nghĩa bởi **class loader khác nhau** là hai `Class<?>` khác nhau. `getMethod` so khớp danh tính kiểu, không so chuỗi tên kiểu. Điều này quan trọng trong plugin framework và môi trường module:

```java
// Chỉ có ý nghĩa nếu Class<?> được load bằng loader của API.
Class<?> parameter = Class.forName(typeName);
Method found = apiType.getMethod(methodName, parameter);
```

Nếu `typeName` được phân giải qua loader không đúng, lookup có thể thất bại dù tên hiển thị giống nhau. Hãy lấy `Class<?>` từ hợp đồng API hoặc class loader phù hợp, không tùy tiện đoán chữ ký bằng runtime type của giá trị.

## 7. Tìm được Method chưa có nghĩa gọi được Method

Hai bước có loại lỗi khác nhau và không nên gom vào một thông báo chung.

### 7.1. Bước tra cứu

```java
Method m = Target.class.getMethod("count", int.class);
```

Nếu không tìm thấy **tên + số lượng + thứ tự + loại tham số**, `getMethod` ném `NoSuchMethodException`. Đổi `int.class` thành `Integer.class` là đổi chữ ký; không có chuyển đổi primitive/wrapper trong lúc lookup.

### 7.2. Bước gọi

```java
Object answer = m.invoke(target, Integer.valueOf(5));
```

Khi đã có `Method`, `invoke` kiểm tra receiver, quyền truy cập, số lượng đối số và khả năng chuyển đổi đối số sang kiểu khai báo. Một số lỗi điển hình:

- `IllegalArgumentException`: sai số lượng đối số; không thể chuyển kiểu; hoặc receiver không phải instance thích hợp của declaring class.
- `IllegalAccessException`: caller không có quyền gọi method tương ứng theo kiểm tra truy cập.
- `InvocationTargetException`: **chính phương thức đích đã ném exception**; dùng `getCause()` để xem lỗi gốc, không gán nhầm là lỗi tra cứu.
- `NullPointerException`: khi gọi instance method với receiver `null`; hoặc xuất hiện sớm hơn nếu bạn tự gọi `value.getClass()` trên `null`.

Ví dụ tách lỗi đích khỏi lỗi reflection:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

Method m = Target.class.getMethod("process", Number.class);
try {
    Object result = m.invoke(target, Integer.valueOf(42));
    System.out.println(result);
} catch (InvocationTargetException wrapped) {
    // Method đã được gọi, nhưng code bên trong method ném lỗi.
    Throwable cause = wrapped.getCause();
    System.err.println("Target threw: " + cause);
}
```

Nếu `process` bị ném exception từ bên trong, `invoke` bọc nó trong `InvocationTargetException`. Điều đó hoàn toàn khác `NoSuchMethodException`, vốn xuất hiện **trước khi có Method để gọi**.

### 7.3. Module boundary trên JDK hiện đại

`getDeclaredMethod` cho phép *tìm* method không public, nhưng quyền *gọi* không tự có. `method.trySetAccessible()` có thể trả `false` khi module không mở package thích hợp; `setAccessible(true)` có thể ném `InaccessibleObjectException` trong môi trường đóng gói mạnh.

Đối với code ứng dụng, ưu tiên API public đã được module export, hoặc thiết kế một adapter/interface rõ ràng. Đừng dựa vào workaround mở toàn bộ module trong production chỉ để gọi private overload. Bài này tập trung vào lựa chọn **public contract**; vấn đề truy cập module là một bước kiểm tra độc lập.

## 8. Quy trình lookup có thể tái sử dụng

Để tránh lỗi, tách phần xác định chữ ký ra khỏi phần lấy giá trị runtime:

```text
Hợp đồng API mô tả:
  methodName = "render"
  parameterTypes = [CharSequence.class]
                |
                v
type.getMethod(name, parameterTypes)
                |
                v
Method cố định: render(CharSequence)
                |
                v
Lấy giá trị từ runtime: "hello" (String)
                |
                v
method.invoke(target, giá trị)
                |
                v
Kiểm tra kết quả hoặc lỗi invoke
```

Nếu một framework dùng cấu hình mô tả chữ ký, nên lưu **kiểu tham số khai báo** (hoặc metadata cho phép giải ra những `Class<?>` đó), không chỉ lưu tên method rồi suy chữ ký từ `arg.getClass()`.

### 8.1. Helper lookup theo hợp đồng

```java
import java.lang.reflect.Method;

static Method requirePublicMethod(
        Class<?> owner, String name, Class<?>... formalTypes)
        throws NoSuchMethodException {
    return owner.getMethod(name, formalTypes);
}

// Một lần resolve rõ ràng, có thể cache Method nếu phù hợp vòng đời loader.
Method formatNumber = requirePublicMethod(
        Target.class, "process", Number.class);
```

Trong hệ thống plugin/hot reload, nếu cache `Method`, phải tính tới vòng đời class loader; giữ `Method` lâu hơn cần thiết có thể giữ cả class loader cũ trong bộ nhớ.

### 8.2. Khi không biết chữ ký, kiểm tra metadata

```java
for (Method method : Target.class.getMethods()) {
    if (!method.getName().equals("process")) continue;

    System.out.println(method.toGenericString());
    System.out.println(Arrays.toString(method.getParameterTypes()));
}
```

`toGenericString()` hữu ích cho log chẩn đoán; không nên parse lại chuỗi log để ra quyết định ứng dụng. Nếu cần kiểm tra, dùng chính `getParameterTypes()`, `getDeclaringClass()`, `isVarArgs()`, `isBridge()` và `isSynthetic()`. Khi dùng `getMethods()`, đừng giả định thứ tự phần tử là ổn định hoặc phản ánh thứ tự khai báo trong mã nguồn.

### 8.3. Nếu có nhiều overload tương thích

Ví dụ `process(Number)` và `process(Object)` đều có thể nhận `Integer`, nhưng không có overload `process(Integer)`. Nếu metadata chỉ cho biết giá trị runtime là `Integer`, **chưa đủ để chọn duy nhất** một method theo yêu cầu nghiệp vụ.

Lựa chọn an toàn là yêu cầu cấu hình khai rõ `process(Number)` hay `process(Object)`. Chỉ tự giải overload nếu bài toán thực sự đòi mô phỏng ngôn ngữ Java, có đặc tả và bộ test đầy đủ cho widening, boxing, varargs, null và ambiguity.

## 9. Bảng chẩn đoán và kiểm thử hợp đồng

| Quan sát | Nguyên nhân thường gặp | Cách sửa đúng |
| --- | --- | --- |
| `NoSuchMethodException` với tham số `Integer.class` | Method khai báo `int` hoặc `Number`, không phải `Integer` | Truyền `int.class` hoặc `Number.class` theo chữ ký |
| `NoSuchMethodException` với `String.class` | Method khai báo `CharSequence` hoặc interface khác | Truyền chính xác `CharSequence.class` |
| `NoSuchMethodException` với class của `List.of(...)` | Method khai báo `List`; runtime class là implementation | Truyền `List.class` |
| `NullPointerException` khi lấy kiểu đối số | Giá trị đối số là `null` | Lấy formal type từ hợp đồng, không gọi `null.getClass()` |
| Không tìm được `join(String, String)` | Formal parameter thứ hai là `String[]` do varargs | Tra cứu `String.class, String[].class` |
| `IllegalArgumentException` khi `invoke` | Sai số lượng hoặc không chuyển đổi được kiểu đối số | Tạo `Object[]` đúng số lượng, kiểu tương thích |
| `getDeclaredMethod` không thấy public method kế thừa | Chỉ tra cứu phương thức khai báo tại lớp đó | Dùng `getMethod` hoặc tra cứu superclass phù hợp |
| `getMethod` không thấy private method | Chỉ tìm public method | Dùng `getDeclaredMethod` để kiểm tra metadata; xem xét quyền truy cập riêng |
| `InvocationTargetException` | Method đích đã chạy và ném exception | Xem `getCause()` và xử lý lỗi nghiệp vụ |
| Có method lạ sau khi liệt kê | Bridge hoặc synthetic method do compiler tạo | Kiểm tra `isBridge()`/`isSynthetic()` |
| Tên class giống nhau nhưng lookup vẫn sai | `Class<?>` lấy từ class loader khác | Resolve kiểu bằng đúng class loader sở hữu API |

### 9.1. Bộ ca kiểm chứng tối thiểu

Hãy có cả ca dương tính và âm tính:

1. **Subtype:** `Integer` gọi được `process(Number)` khi lookup bằng `Number.class`; lookup bằng `Integer.class` phải thất bại nếu không có overload đó.
2. **Interface:** `String` gọi được `render(CharSequence)` nhưng lookup bằng `String.class` phải thất bại nếu không có `render(String)`.
3. **Primitive:** `count(int)` tra cứu bằng `int.class`, gọi bằng `Integer` sau unboxing; tra cứu bằng `Integer.class` phải thất bại.
4. **Widening ở invocation:** `widen(long)` có thể gọi với `Integer` nhờ unboxing + widening; lookup vẫn phải dùng `long.class`.
5. **Null:** chọn rõ `choose(String)` hoặc `choose(Object)` rồi gọi với một đối số null; không suy kiểu từ giá trị.
6. **Varargs:** tra cứu `join(String, String[])` và truyền `String[]`; kiểm tra `isVarArgs()`.
7. **Generics:** `accept(List<String>)` lookup bằng `List.class`, không bằng kiểu implementation của `List.of(...)`.
8. **Access:** `getDeclaredMethod` nhìn thấy private method; `getMethod` không tìm nó.
9. **Inheritance:** `getMethod` tìm public inherited method; `getDeclaredMethod` trên child không tìm method chỉ thuộc parent.

**Tiêu chí hoàn thành:** mọi ca dương tính gọi đúng method và mọi ca âm tính thất bại bằng lỗi **dự kiến**, không phụ thuộc thứ tự liệt kê method hay tên runtime của implementation class.

## 10. Nguyên tắc thiết kế và kết luận

Trong ứng dụng thật, reflection phù hợp khi cần làm việc với lớp hoặc method chỉ biết lúc chạy, ví dụ framework mapping, plugin hay adapter. Tuy nhiên, khi mã Java đã biết rõ kiểu API, lời gọi có kiểu tĩnh hoặc interface thường dễ đọc, dễ được compiler kiểm tra và dễ bảo trì hơn reflection.

Khi bắt buộc dùng reflection, hãy giữ các nguyên tắc sau:

- **Chữ ký là hợp đồng:** lấy `Class<?>` từ kiểu tham số khai báo của API.
- **Giá trị là input:** kiểm tra nó có tương thích với chữ ký đã chọn, nhưng không dùng `arg.getClass()` để thay thế chữ ký.
- **Tách lookup và invocation:** `NoSuchMethodException` khác `IllegalArgumentException` hoặc `InvocationTargetException`.
- **Primitive, varargs và generic có biểu diễn riêng:** `int.class` khác `Integer.class`; varargs là array; generic bị erasure.
- **Không phụ thuộc chi tiết compiler:** chú ý bridge/synthetic method và class loader trong hệ thống mở rộng.
- **Tôn trọng module boundary:** lookup được không đồng nghĩa với quyền gọi.
- **Viết test xác minh:** đặc biệt khi hỗ trợ nhiều JDK, nhiều provider hoặc implementation của cùng interface.

Đây là hợp đồng reflection đã tồn tại lâu trong Java và **tiếp tục áp dụng trên JDK hiện đại**. Nó giúp tránh lỗi khó phát hiện khi giá trị runtime hợp lệ để gọi một phương thức nhưng không thể dùng để xác định đúng overload mà API công bố.

### Tài liệu tham khảo

- [Class.getMethod / Class.getDeclaredMethod — Java SE](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html): tra cứu public và declared method bằng tên, danh sách parameter types.
- [Method.invoke — Java SE](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Method.html): điều kiện gọi, conversion, exception và `isBridge()`/`isVarArgs()`.
- [AccessibleObject — Java SE](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AccessibleObject.html): kiểm tra khả năng truy cập trên hệ thống module.
- [Java Language Specification — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12): overload resolution ở lời gọi Java.
- [Java Language Specification — Type Erasure](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.6): erasure của generic type.
