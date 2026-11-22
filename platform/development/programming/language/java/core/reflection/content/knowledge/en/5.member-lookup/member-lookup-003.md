# Java Reflection: tra cứu thành viên bằng `getDeclaredField()`, `getDeclaredMethod()` và `getDeclaredConstructor()`

Khi đã có một đối tượng `Class<?>`, Reflection cho phép tra cứu chính xác **field**, **method** và **constructor** được **khai báo trực tiếp** trong kiểu đó. Ba phương thức `getDeclaredField()`, `getDeclaredMethod()` và `getDeclaredConstructor()` là công cụ chính cho công việc này. Chúng có thể tìm thấy cả thành viên `private`, `protected`, package-private và `public`, nhưng **việc tìm được thành viên không tự động cho phép đọc, gọi hoặc khởi tạo qua thành viên ấy**.

Bài học tập trung vào tra cứu thành viên theo tên/chữ ký, khác biệt giữa thành viên khai báo và thành viên kế thừa, cách xử lý chữ ký phương thức chính xác, kết quả trả về, ngoại lệ, và quyền truy cập khi sử dụng đối tượng Reflection đã tìm được.

## 1. Từ `Class<?>` tới ba loại thành viên

Ba API nằm trên `java.lang.Class`:

| API | Đối tượng trả về | Điều kiện tra cứu | Không bao gồm |
| --- | --- | --- | --- |
| `getDeclaredField(String name)` | `Field` | Field có tên `name`, khai báo trực tiếp trong lớp/interface đang xét | Field chỉ được kế thừa từ superclass |
| `getDeclaredMethod(String name, Class<?>... parameterTypes)` | `Method` | Method khai báo trực tiếp, đúng tên và đúng **dãy kiểu tham số** | Method chỉ được kế thừa; phương thức cùng tên nhưng sai kiểu/số lượng tham số |
| `getDeclaredConstructor(Class<?>... parameterTypes)` | `Constructor<T>` | Constructor được khai báo bởi lớp, với dãy kiểu tham số yêu cầu | Constructor của lớp cha; constructor có chữ ký khác |

Cú pháp điển hình:

~~~java
Class<?> type = Example.class;

Field field = type.getDeclaredField("value");
Method method = type.getDeclaredMethod("convert", String.class, int.class);
Constructor<?> constructor = type.getDeclaredConstructor(String.class);
~~~

Đây là **đoạn mã minh họa API**; nó chỉ hoạt động khi lớp `Example` thực sự có các khai báo tương ứng. Nếu không tìm thấy thành viên, phương thức sẽ ném checked exception (`NoSuchFieldException` hoặc `NoSuchMethodException`).

Cụm từ *declared* có hai ý nghĩa cần nhớ:

1. **Không lọc theo mức truy cập:** thành viên `private` vẫn có thể được tìm thấy dưới dạng `Field`, `Method` hoặc `Constructor`.
2. **Chỉ xét khai báo trực tiếp:** field và method nằm ở lớp cha không xuất hiện khi tra cứu `getDeclaredField`/`getDeclaredMethod` trên lớp con. Constructor vốn không được kế thừa.

Các phương thức có dạng số nhiều là `getDeclaredFields()`, `getDeclaredMethods()`, `getDeclaredConstructors()`. Chúng dùng để khám phá toàn bộ thành viên được khai báo; khi đã biết tên/chữ ký thì nên dùng API số ít để tra cứu đúng mục tiêu. Thứ tự phần tử trong mảng kết quả `getDeclared*()` số nhiều không được đảm bảo.

## 2. `getDeclaredField(String name)`: tìm field theo tên

`getDeclaredField("code")` tìm trường tên `code` trực tiếp trên đối tượng `Class` đang xét. Nó trả về `java.lang.reflect.Field`, từ đó có thể đọc metadata:

- `field.getName()`: tên field.
- `field.getType()`: kiểu runtime của field dưới dạng `Class<?>`.
- `field.getGenericType()`: metadata của kiểu generic khi có.
- `field.getDeclaringClass()`: lớp/interface thực sự khai báo field.
- `field.getModifiers()`: cờ truy cập và các modifier; sử dụng `Modifier.isPrivate(...)`, `Modifier.isStatic(...)` khi cần.
- `field.get(target)` hoặc các phương thức như `field.getInt(target)`: đọc giá trị **sau khi thỏa quy tắc truy cập**.

Field không có danh sách tham số hay overload theo chữ ký. Một lớp Java không thể khai báo hai field trùng tên trong cùng một khai báo lớp hợp lệ; nhưng lớp con có thể **che khuất** field cùng tên của lớp cha. Khi đó `Child.class.getDeclaredField("code")` tìm field của `Child`, còn `Parent.class.getDeclaredField("code")` tìm field của `Parent` nếu mỗi lớp tự khai báo field ấy.

**Sai lầm thường gặp:** cho rằng `Child.class.getDeclaredField("inherited")` tìm được field của `Parent`. Đây là yêu cầu ngoài phạm vi *declared*. Nếu field là `public`, `Child.class.getField("inherited")` có thể tìm thấy field kế thừa; nếu không phải public, phải duyệt `getSuperclass()` theo đúng yêu cầu nghiệp vụ rồi tra cứu trên lớp khai báo.

## 3. `getDeclaredMethod(String name, Class<?>... parameterTypes)`: tên + chữ ký tham số

Để tìm một method cụ thể, truyền tên phương thức và các `Class<?>` biểu diễn **kiểu tham số khai báo theo đúng thứ tự**:

~~~java
type.getDeclaredMethod("save", String.class, int.class);
type.getDeclaredMethod("refresh"); // Method không có tham số
~~~

Những quy tắc quan trọng:

- Phân biệt **số lượng và thứ tự tham số**: `save(String,int)` khác `save(int,String)`.
- Phân biệt **primitive và wrapper**: `int.class` khác `Integer.class`.
- Phân biệt **mảng và phần tử**: `String[].class` khác `String.class`.
- Tham số `String... values` ở mã nguồn được biểu diễn là `String[]` ở chữ ký Reflection; khi tra cứu phải dùng `String[].class`, không truyền nhiều đối số `String.class`.
- Không áp dụng tự động *autoboxing*, *widening* (`int` sang `long`), hay chuyển kiểu khi **tra cứu**. Những quy tắc này của lời gọi Java thông thường không dùng để dò ra method ở đây.
- Với tham số generic như `List<String>`, chữ ký runtime chịu *type erasure*: tra cứu bằng `List.class`. Dùng `getGenericParameterTypes()` trên `Method` nếu cần phân tích metadata generic.
- **Không truyền kiểu trả về** vào `getDeclaredMethod`. API nhận tên và kiểu tham số; sau khi lấy `Method`, đọc `method.getReturnType()` hoặc `getGenericReturnType()` để kiểm tra kiểu kết quả. Trong bytecode có thể tồn tại bridge/synthetic method; không nên suy đoán danh sách `getDeclaredMethods()` chỉ gồm các method tự viết trong mã nguồn.

Nếu hai overload là `parse(String)` và `parse(int)`, tên giống nhau nhưng đối số `String.class` và `int.class` giúp chọn đúng method. Method `static` vẫn tra cứu bằng cách tương tự, rồi có thể kiểm tra `Modifier.isStatic(method.getModifiers())`.

## 4. `getDeclaredConstructor(Class<?>... parameterTypes)`: tra cứu constructor

Constructor không có tên method riêng trong lời gọi này: chỉ cần truyền danh sách kiểu tham số của constructor.

~~~java
Constructor<?> noArg = type.getDeclaredConstructor();
Constructor<?> withName = type.getDeclaredConstructor(String.class);
~~~

`getDeclaredConstructor()` không tham số yêu cầu **constructor thật sự không tham số**; nó không có nghĩa là "lấy constructor bất kỳ" hay "tạo constructor mặc định". Nếu lớp chỉ khai báo `Example(String)`, tra cứu `getDeclaredConstructor()` sẽ ném `NoSuchMethodException`. Nếu Java tự tạo constructor mặc định, constructor đó có thể tìm thấy khi chữ ký khớp.

Khác với method/field, constructor **không được kế thừa**. Vì vậy `getDeclaredConstructor` và `getConstructor` đều chỉ áp dụng cho constructor của chính lớp đang được xét; sự khác biệt lớn là `getConstructor` chỉ tìm constructor `public`, còn `getDeclaredConstructor` có thể tìm constructor không `public`.

Một số trường hợp cần biết:

- Lớp `abstract` vẫn có constructor để lớp con gọi qua `super(...)`, nhưng không thể khởi tạo trực tiếp bằng `Constructor#newInstance`.
- Lớp thành viên **không `static`** có thể có tham số ẩn biểu diễn đối tượng lớp bao ngoài. Ví dụ constructor mã nguồn `Outer.Inner(int)` thường xuất hiện trong Reflection dưới dạng tham số `Outer.class, int.class`. Khi không thấy chữ ký dự đoán, xem `getParameterTypes()` của các constructor được khai báo.
- Enum và một số lớp do compiler sinh có chi tiết constructor đặc biệt; không giả định mọi chữ ký runtime giống hệt mã nguồn.

## 5. Ví dụ đầy đủ: declared khác inherited thế nào?

Tạo tệp **`DeclaredLookupDemo.java`**. Trong cùng tệp này, chỉ `DeclaredLookupDemo` là lớp `public`; hai lớp hỗ trợ dùng tên riêng để tránh phụ thuộc cấu trúc package:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

class LookupParent {
    public String inheritedField = "parent";

    public void inheritedMethod() {
    }
}

class LookupChild extends LookupParent {
    private String code;

    private LookupChild(String code) {
        this.code = code;
    }

    private String convert(String input) {
        return input.toUpperCase();
    }

    public int convert(int number) {
        return number * 2;
    }
}

public class DeclaredLookupDemo {
    public static void main(String[] args) throws ReflectiveOperationException {
        Class<LookupChild> type = LookupChild.class;

        Field field = type.getDeclaredField("code");
        Method stringMethod = type.getDeclaredMethod("convert", String.class);
        Method intMethod = type.getDeclaredMethod("convert", int.class);
        Constructor<LookupChild> constructor =
                type.getDeclaredConstructor(String.class);

        System.out.println("Field: " + field.getName()
                + " -> " + field.getType().getSimpleName());
        System.out.println("Method 1: " + stringMethod.getName()
                + "(String) -> " + stringMethod.getReturnType().getSimpleName());
        System.out.println("Method 2: " + intMethod.getName()
                + "(int) -> " + intMethod.getReturnType().getSimpleName());
        System.out.println("Constructor: "
                + constructor.getDeclaringClass().getSimpleName()
                + "(String)");

        try {
            type.getDeclaredField("inheritedField");
        } catch (NoSuchFieldException expected) {
            System.out.println("Declared inheritedField: not found");
        }

        System.out.println("Public inherited field: "
                + type.getField("inheritedField")
                        .getDeclaringClass().getSimpleName());

        try {
            type.getDeclaredMethod("inheritedMethod");
        } catch (NoSuchMethodException expected) {
            System.out.println("Declared inheritedMethod: not found");
        }

        System.out.println("Public inherited method: "
                + type.getMethod("inheritedMethod")
                        .getDeclaringClass().getSimpleName());
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac DeclaredLookupDemo.java
java DeclaredLookupDemo
~~~

**Stdout:**

~~~text
Field: code -> String
Method 1: convert(String) -> String
Method 2: convert(int) -> int
Constructor: LookupChild(String)
Declared inheritedField: not found
Public inherited field: LookupParent
Declared inheritedMethod: not found
Public inherited method: LookupParent
~~~

Vì sao kết quả như trên?

1. `code`, hai overload `convert` và constructor `LookupChild(String)` đều **được khai báo trực tiếp** trong `LookupChild`, nên ba API `getDeclared...` tìm được chúng bất kể `private` hay `public`.
2. `inheritedField` và `inheritedMethod` **chỉ khai báo tại `LookupParent`**; tìm bằng `getDeclared...` trên `LookupChild` thất bại.
3. Cả hai thành viên kế thừa là `public`, nên `getField`/`getMethod` trên `LookupChild` trả về thành viên có `getDeclaringClass() == LookupParent.class`.

Chú ý: ví dụ này **chỉ tra cứu và in metadata**, chưa đọc trực tiếp field `code`, chưa gọi `convert`, chưa tạo `LookupChild` từ private constructor. Đây là ranh giới quan trọng giữa *lookup* và *access*.

## 6. Tra cứu không đồng nghĩa quyền truy cập: `trySetAccessible()`

Một `Field`, `Method` hoặc `Constructor` được tìm bằng `getDeclared...` vẫn chịu quy tắc truy cập khi dùng `Field#get`/`set`, `Method#invoke` hoặc `Constructor#newInstance`. Với thành viên không thể truy cập từ mã gọi, một số thao tác có thể ném `IllegalAccessException` nếu không được cấp quyền thích hợp.

Lớp cơ sở `AccessibleObject` hỗ trợ:

- `canAccess(target)`: kiểm tra quyền truy cập hiện tại đối với thành viên; truyền đối tượng đích cho thành viên instance, `null` cho thành viên static và constructor.
- `trySetAccessible()`: thử bật quyền bỏ qua kiểm tra truy cập Java và trả `true` nếu thành công, `false` nếu không thể cấp. Việc thử này **không bảo đảm thành công**.
- `setAccessible(true)`: yêu cầu bật quyền bỏ qua kiểm tra; có thể ném `InaccessibleObjectException` trong trường hợp Java modules không cho phép.

Ví dụ sau chạy dưới dạng ứng dụng không khai báo `module-info.java` (unnamed module), nên mã ứng dụng trong ví dụ có thể truy cập sâu vào chính các lớp của nó. Tạo tệp **`DeclaredAccessDemo.java`**:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

class SecretBox {
    private String value;

    private SecretBox(String value) {
        this.value = value;
    }

    private String reveal(String suffix) {
        return value + suffix;
    }
}

public class DeclaredAccessDemo {
    public static void main(String[] args) throws ReflectiveOperationException {
        Class<SecretBox> type = SecretBox.class;

        Constructor<SecretBox> constructor =
                type.getDeclaredConstructor(String.class);
        System.out.println("Constructor access: "
                + constructor.trySetAccessible());

        SecretBox box = constructor.newInstance("data");

        Field field = type.getDeclaredField("value");
        System.out.println("Field access: " + field.trySetAccessible());
        System.out.println("Field value: " + field.get(box));

        Method method = type.getDeclaredMethod("reveal", String.class);
        System.out.println("Method access: " + method.trySetAccessible());
        System.out.println("Method result: " + method.invoke(box, "!"));
    }
}
~~~

~~~bash
javac DeclaredAccessDemo.java
java DeclaredAccessDemo
~~~

**Stdout trong điều kiện chạy được nêu:**

~~~text
Constructor access: true
Field access: true
Field value: data
Method access: true
Method result: data!
~~~

**Giải thích luồng thực thi:**

1. Tìm private constructor theo đúng `String.class` rồi gọi `trySetAccessible()` trước khi `newInstance("data")`.
2. Tìm private field `value`, thử cấp quyền, sau đó đọc bằng `field.get(box)`.
3. Tìm private method `reveal(String)`, thử cấp quyền, rồi gọi `method.invoke(box, "!")`. Kết quả trả về kiểu `Object`; ở đây chuỗi kết quả là `data!`.

Trong chương trình thực tế, phải **kiểm tra** kết quả `trySetAccessible()` trước khi thao tác. Nếu trả `false`, không được giả định thao tác sẽ thành công. Tránh mở quyền phản chiếu cho dữ liệu không tin cậy và không cần thiết; ưu tiên API `public` nếu có thể.

### Java Platform Module System (JPMS) từ Java 9

Quyền truy cập Reflection còn bị giới hạn bởi ranh giới module. Một package được khai báo `exports` thường cho phép các module đọc thành viên `public` theo quy tắc truy cập thông thường; để thực hiện **deep reflection** tới thành viên không `public` ở module khác, package thường phải được `opens` phù hợp cho module thực hiện Reflection (hoặc có cơ chế cấp phép tương đương). `getDeclaredMethod()` vẫn có thể trả về metadata nhưng `trySetAccessible()` có thể trả `false`, còn `setAccessible(true)` có thể ném `InaccessibleObjectException`. Không dùng `--add-opens` như giải pháp mặc định cho mã ứng dụng; việc mở package cần quyết định rõ ràng ở ranh giới module.

## 7. Ví dụ chữ ký chính xác: varargs, primitive/wrapper, generic erasure

Tạo tệp **`ExactSignatureDemo.java`**:

~~~java
import java.lang.reflect.Method;
import java.util.List;

class SignatureTarget {
    private void run(int count, String... tags) {
    }

    private void accept(List<String> values) {
    }
}

public class ExactSignatureDemo {
    public static void main(String[] args) throws NoSuchMethodException {
        Class<SignatureTarget> type = SignatureTarget.class;

        Method run = type.getDeclaredMethod(
                "run", int.class, String[].class);
        Method accept = type.getDeclaredMethod("accept", List.class);

        System.out.println("Found: " + run.getName());
        System.out.println("Varargs: " + run.isVarArgs());
        System.out.println("Generic erased parameter: "
                + accept.getParameterTypes()[0].getName());

        try {
            type.getDeclaredMethod("run", Integer.class, String[].class);
        } catch (NoSuchMethodException expected) {
            System.out.println("Integer.class instead of int.class: not found");
        }
    }
}
~~~

~~~bash
javac ExactSignatureDemo.java
java ExactSignatureDemo
~~~

**Stdout:**

~~~text
Found: run
Varargs: true
Generic erased parameter: java.util.List
Integer.class instead of int.class: not found
~~~

Điều này cho thấy `String...` là `String[]` ở chữ ký Reflection; `int.class` không tương đương `Integer.class` khi **dò phương thức**; và `List<String>` dùng `List.class` sau type erasure. Nếu cần tham số `List<String>` ở mức khai báo, có thể tiếp tục đọc `accept.getGenericParameterTypes()`.

Các overload không được xét theo khả năng chuyển đổi ở lúc gọi. Chẳng hạn mã Java có thể chọn một overload nhờ chuyển `int` thành `long`, nhưng `getDeclaredMethod("run", long.class, ...)` **không** tìm được `run(int, ...)`.

## 8. Xác định đúng lớp khai báo khi cần đi lên phân cấp

Khi `Child.class.getDeclaredField("id")` không tìm thấy field nằm ở `Parent`, việc đổi sang `getField("id")` chỉ giải quyết được nếu field ấy là `public`. Với field non-public, hãy tra cứu trên đúng kiểu khai báo như `Parent.class.getDeclaredField("id")` hoặc tự duyệt `getSuperclass()` theo chính sách nghiệp vụ. Phân biệt tương tự áp dụng cho method, trong khi constructor không được kế thừa.

Nếu lớp con che field cùng tên của lớp cha, hai `Field` vẫn tồn tại riêng; dùng `getDeclaringClass()` để biết chủ sở hữu. Việc tìm thấy metadata vẫn chưa bảo đảm được phép đọc/ghi/gọi: hãy kiểm tra quyền truy cập như ở mục 6. Chủ đề duyệt nhiều tầng và giải quyết xung đột được phát triển ở bài xây dựng chính sách tìm kiếm xuyên phân cấp.

## 9. Ngoại lệ và quy trình xử lý lỗi

| Thao tác | Tình huống | Cần xử lý |
| --- | --- | --- |
| `getDeclaredField("x")` | Không có field tên `x` trực tiếp trên kiểu | `NoSuchFieldException` (checked) |
| `getDeclaredMethod("m", ...)` | Sai tên hoặc sai kiểu/số lượng/thứ tự tham số | `NoSuchMethodException` (checked) |
| `getDeclaredConstructor(...)` | Không có constructor đúng chữ ký | `NoSuchMethodException` (checked) |
| `Field#get`, `Method#invoke`, `Constructor#newInstance` | Không có quyền truy cập thành viên | Có thể `IllegalAccessException` |
| `Method#invoke` | Chính method được gọi ném ngoại lệ | `InvocationTargetException` bọc ngoại lệ gốc; dùng `getCause()` |
| `Constructor#newInstance` | Constructor chạy và ném ngoại lệ | `InvocationTargetException` bọc ngoại lệ gốc |
| `setAccessible(true)` | JPMS hoặc giới hạn khác từ chối mở quyền | Có thể `InaccessibleObjectException` (runtime) |

Lỗi sai chữ ký thường nên được xử lý ở **bước tra cứu**, thay vì chỉ bắt ngoại lệ chung sau khi gọi. Ví dụ:

~~~java
try {
    Method method = type.getDeclaredMethod("process", String.class);
    // Kiểm tra modifiers, quyền truy cập, kiểu trả về trước khi invoke.
} catch (NoSuchMethodException e) {
    // Tên "process" hoặc chữ ký (String) không được khai báo tại type.
}
~~~

Đoạn trên giả sử biến `type` là một `Class<?>` hợp lệ. Trong chương trình lớn, nên ghi rõ tên lớp, tên thành viên và danh sách kiểu tham số trong thông báo lỗi (cẩn thận không log dữ liệu bí mật); điều này giúp phân biệt "không tìm thấy" với "tìm thấy nhưng không đủ quyền".

### Checklist khi tra cứu thất bại

1. **Đúng `Class<?>` chưa?** `getDeclared...` không tự đi lên lớp cha.
2. **Đúng chính tả và hoa/thường?** Tên thành viên phân biệt chữ hoa/chữ thường.
3. **Đúng số lượng/thứ tự/loại tham số?** `int.class`, `Integer.class`, `String.class` và `String[].class` là các kiểu khác nhau.
4. **Có constructor không tham số thật không?** `getDeclaredConstructor()` không tạo constructor mới.
5. **Lớp lồng không `static` có tham số lớp bao ngoài không?** Khám phá `getDeclaredConstructors()` và `getParameterTypes()`.
6. **Generic có bị xóa kiểu không?** `List<String>` trong tham số runtime tương ứng `List.class`.
7. **Đã tìm thấy nhưng không sử dụng được?** Kiểm tra `canAccess`, `trySetAccessible`, ranh giới module và ngoại lệ khi invoke/newInstance.

## 10. Mở rộng: metadata và các thành viên compiler sinh

Các đối tượng tìm được tiếp tục cung cấp thông tin hữu ích:

- `Field#getDeclaringClass()`, `Method#getDeclaringClass()` và `Constructor#getDeclaringClass()` xác định lớp/interface khai báo.
- `Method#getParameterTypes()` và `Constructor#getParameterTypes()` trả về dãy kiểu `Class<?>` theo chữ ký runtime. `getGenericParameterTypes()` cung cấp dạng `Type[]` để quan sát metadata generic.
- `Method#isBridge()` nhận biết bridge method do compiler sinh cho một số trường hợp generic/override; `Member#isSynthetic()` có thể giúp nhận biết thành viên do compiler tạo. Không suy ra rằng mọi thành viên xuất hiện trong Reflection đều là một khai báo viết tay trong nguồn.
- `Modifier.toString(member.getModifiers())` cho mô tả modifier. Ví dụ `private static`, `public final`; không nên đối chiếu modifier bằng phép so sánh chuỗi nếu chỉ cần kiểm tra một cờ cụ thể.

Đối với framework đọc metadata, một quy trình rõ ràng là: xác định `Class<?>` → lựa chọn `getDeclared...` hoặc `get...` theo phạm vi → dùng tên/chữ ký chính xác → kiểm tra loại và modifier → kiểm tra quyền truy cập → mới thao tác với giá trị hay gọi thành viên. Đừng mặc định thêm `setAccessible(true)` ở mọi nơi; thao tác này có thể thất bại hoặc không được phép theo ranh giới module.

## 11. Tự kiểm tra hiểu bài

**Câu hỏi 1.** Lớp `Child` kế thừa `public void ping()` từ `Parent` nhưng không override. `Child.class.getDeclaredMethod("ping")` thành công không?

**Đáp án:** Không; nó ném `NoSuchMethodException`. `Child.class.getMethod("ping")` có thể tìm phương thức `public` được kế thừa.

**Câu hỏi 2.** Vì sao `getDeclaredMethod("send", Integer.class)` không tìm được method khai báo `send(int)`?

**Đáp án:** Lookup so khớp `Class<?>` tham số chính xác, không áp dụng autoboxing; phải truyền `int.class`.

**Câu hỏi 3.** Nếu một class chỉ có constructor `private Item(String)`, phương thức nào tìm được constructor này?

**Đáp án:** `Item.class.getDeclaredConstructor(String.class)`. `getConstructor(String.class)` yêu cầu constructor `public`; `getDeclaredConstructor()` lại yêu cầu không có tham số.

**Câu hỏi 4.** Tìm được `private Field` bằng `getDeclaredField` đã có thể đọc giá trị ngay chưa?

**Đáp án:** Chưa chắc. Reflection lookup trả metadata; khi đọc field vẫn có quy tắc truy cập và JPMS. Chỉ thử `trySetAccessible()` khi thật sự cần và xử lý trường hợp bị từ chối.

**Câu hỏi 5.** Phương thức khai báo `void add(String... tags)` được tra cứu bằng những tham số nào?

**Đáp án:** `type.getDeclaredMethod("add", String[].class)` vì varargs được biểu diễn thành một tham số kiểu mảng ở chữ ký runtime.

**Ghi nhớ:** ba API `getDeclared...` trả lời câu hỏi *"Thành viên được khai báo trực tiếp trên kiểu này là gì?"*. Độ chính xác nằm ở tên field, tên cộng danh sách kiểu tham số method, hoặc danh sách kiểu tham số constructor. Sau lookup, hãy kiểm tra metadata và quyền truy cập trước khi làm việc với giá trị hoặc thực thi thành viên.
