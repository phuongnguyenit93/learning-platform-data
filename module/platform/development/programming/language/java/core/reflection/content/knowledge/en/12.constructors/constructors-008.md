# Tham số ngầm định hoặc synthetic của constructor trong Java Reflection

## 1. Vì sao chữ ký constructor khi Reflection có thể khác phần ta viết?

Khi nhìn mã nguồn, ta thường nghĩ constructor có đúng những tham số được viết giữa cặp dấu ngoặc. Ví dụ:

```java
class Outer {
    class Inner {
        Inner(String message) {}
    }
}
```

Trong mã Java, ta viết `outer.new Inner("Hello")`: danh sách đối số hiển thị của `Inner` chỉ có một `String`. Tuy nhiên, Java còn cần biết **instance `Outer` bao quanh** đối tượng `Inner`. Bộ biên dịch thể hiện mối liên hệ này trong constructor của classfile bằng **một tham số đầu bổ sung**. Khi Reflection tra cứu constructor, chữ ký có thể là `(Outer, String)`, chứ không phải chỉ `(String)`.

Những tham số không xuất hiện trực tiếp như một khai báo thông thường trong source còn có thể xuất hiện ở **enum constructor** hoặc constructor do compiler sinh cho **local/anonymous class** có captured variables. Reflection cho ta thấy chữ ký thực tế của executable trong classfile; một framework xây dựng đối số chỉ dựa vào khai báo source có thể tìm sai constructor hoặc truyền sai thứ tự giá trị.

Điều cần phân biệt là:

- **Explicit parameter:** tham số được lập trình viên khai báo tường minh, ví dụ `String message`.
- **Implicit parameter:** tham số được ngôn ngữ xem là được khai báo ngầm định; ví dụ tham chiếu enclosing instance của một non-static member inner class.
- **Synthetic parameter:** tham số do compiler đưa vào mà không được khai báo tường minh hay ngầm định theo định nghĩa của Java; ví dụ hai tham số nội bộ của enum, hoặc captured local value trong bytecode do `javac` sinh.

Tên tham số, cờ `implicit`/`synthetic` và cách compiler lưu classfile cần được kiểm tra đúng ở metadata thay vì đoán theo tên như `this$0`, `arg0` hoặc `val$...`.

## 2. API Reflection dành cho constructor và từng tham số

Đối tượng `java.lang.reflect.Constructor<?>` có các API quan trọng:

| API | Ý nghĩa |
| --- | --- |
| `Class.getDeclaredConstructors()` | Lấy mọi constructor khai báo trong kiểu, bất kể access modifier |
| `Class.getDeclaredConstructor(Class<?>...)` | Tìm một constructor theo **toàn bộ** các kiểu tham số thực tế và đúng thứ tự |
| `Class.getConstructors()` | Chỉ các constructor public của class |
| `Constructor.getParameterCount()` | Tổng số tham số của executable, bao gồm các vị trí compiler bổ sung xuất hiện trong chữ ký |
| `Constructor.getParameterTypes()` | Mảng kiểu tham số `Class<?>[]` theo đúng thứ tự |
| `Constructor.getParameters()` | Mảng `java.lang.reflect.Parameter` có metadata của từng vị trí |
| `Parameter.getType()` | Kiểu tham số dạng `Class<?>` |
| `Parameter.getName()` | Tên metadata hoặc tên tổng hợp như `arg0` |
| `Parameter.isNamePresent()` | Tên có được lưu trong metadata của classfile không |
| `Parameter.isImplicit()` | Tham số được khai báo ngầm định theo Java Language Specification |
| `Parameter.isSynthetic()` | Tham số do compiler sinh, không được khai báo tường minh hoặc ngầm định |

Hai method `isImplicit()` và `isSynthetic()` diễn đạt **hai loại khác nhau** theo đặc tả `Parameter`. Đừng xem chúng là hai tên gọi tương đương cho mọi tham số “ẩn”. Cả hai cùng có thể là `false` với tham số explicit bình thường.

Phân biệt thêm: `constructor.isSynthetic()` hỏi **bản thân constructor** có synthetic không; `constructor.getParameters()[i].isSynthetic()` hỏi **tham số thứ i** có synthetic không. Một constructor không phải synthetic vẫn có thể chứa synthetic parameters.

## 3. Trường hợp 1: non-static member inner class cần enclosing instance

### 3.1. Tại sao có tham số `Outer` ở đầu?

Một **non-static member class** gắn với một enclosing instance. Cú pháp Java thông thường:

```java
Outer outer = new Outer();
Outer.Inner inner = outer.new Inner("Hello");
```

đã cung cấp `outer` thông qua biểu thức `outer.new`. Trong biểu diễn constructor của classfile, enclosing instance thường là **tham số thứ nhất**, rồi mới đến tham số source `String`. Ví dụ:

```text
Constructor source: Inner(String)
Constructor Reflection: Inner(Outer, String)
```

Để tra cứu bằng Reflection, ta cần dùng:

```java
Constructor<Outer.Inner> ctor =
        Outer.Inner.class.getDeclaredConstructor(Outer.class, String.class);
```

Đây là **đoạn minh họa**, giả sử `Outer.Inner` và constructor tương ứng được khai báo với mức truy cập cho phép. Nếu constructor không public, cần kiểm tra access; `getDeclaredConstructor` tìm được metadata nhưng không tự cấp quyền gọi.

Không phải mọi class lồng nhau đều cần enclosing instance: **static nested class** không có yêu cầu này. Một class được khai báo `static class Nested` có constructor `Nested(String)` sẽ không tự nhận thêm tham số kiểu `Outer` chỉ vì nó được đặt trong source của `Outer`.

### 3.2. Ví dụ Java 17+ độc lập, có thể biên dịch

Tạo file **`ConstructorParametersDemo.java`**:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;
import java.util.Arrays;

public class ConstructorParametersDemo {
    class Inner {
        final String value;
        Inner(String value) {
            this.value = value;
        }
    }

    static class Nested {
        Nested(String value) {}
    }

    enum Level {
        HIGH(10);
        Level(int priority) {}
    }

    private static void show(Class<?> type) {
        for (Constructor<?> ctor : type.getDeclaredConstructors()) {
            System.out.println("Type: " + type.getSimpleName());
            System.out.println("Parameter count: " + ctor.getParameterCount());
            for (Parameter p : ctor.getParameters()) {
                System.out.printf(
                        "  %s | %s | implicit=%s synthetic=%s namePresent=%s%n",
                        p.getName(), p.getType().getSimpleName(),
                        p.isImplicit(), p.isSynthetic(), p.isNamePresent()
                );
            }
        }
    }

    public static void main(String[] args) throws Exception {
        show(Inner.class);
        show(Nested.class);
        show(Level.class);

        Constructor<Inner> ctor = Inner.class.getDeclaredConstructor(
                ConstructorParametersDemo.class, String.class
        );
        ctor.setAccessible(true);
        Inner instance = ctor.newInstance(new ConstructorParametersDemo(), "ok");
        System.out.println("Inner value: " + instance.value);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -parameters ConstructorParametersDemo.java
java ConstructorParametersDemo
```

Kết quả stdout với **`javac 21 --release 17 -parameters`**:

```text
Type: Inner
Parameter count: 2
  this$0 | ConstructorParametersDemo | implicit=true synthetic=false namePresent=true
  value | String | implicit=false synthetic=false namePresent=true
Type: Nested
Parameter count: 1
  value | String | implicit=false synthetic=false namePresent=true
Type: Level
Parameter count: 3
  $enum$name | String | implicit=false synthetic=true namePresent=true
  $enum$ordinal | int | implicit=false synthetic=true namePresent=true
  priority | int | implicit=false synthetic=false namePresent=true
Inner value: ok
```

**Đọc kết quả theo từng lớp:**

- `Inner` có **hai** tham số Reflection, dù mã nguồn khai báo một tham số `value`. Vị trí đầu là enclosing instance kiểu `ConstructorParametersDemo`. `isImplicit() == true`; ở bản build đã kiểm tra, `isSynthetic() == false`.
- `Nested` là static nested class nên chỉ có `String value`, không cần object bên ngoài.
- `Level` là enum: trước tham số explicit `int priority` có hai tham số nội bộ `String` và `int`; với `javac` đang dùng, chúng được đánh dấu `synthetic=true`.
- Lời gọi `ctor.newInstance(new ConstructorParametersDemo(), "ok")` cung cấp **đúng thứ tự**: enclosing instance trước, `String` sau, nên tạo `Inner` thành công.

Ví dụ cố ý gọi `setAccessible(true)` vì constructor `Inner` có package-private access và được tra cứu bằng `getDeclaredConstructor`. Trong ngữ cảnh ví dụ này, code được chạy trên classpath trong unnamed module và cùng class bao ngoài; không được suy luận rằng `setAccessible(true)` luôn được phép xuyên qua mọi module.

Tên `this$0` và `$enum$name` là chi tiết sinh bởi compiler trong phiên bản được kiểm tra; **không nên dùng tên ấy làm hợp đồng API lâu dài**. Metadata ổn định hơn cho thao tác lựa chọn constructor là **vị trí, kiểu tham số và đặc tính của executable**.

## 4. Trường hợp 2: enum constructor có tham số nội bộ

Xét:

```java
enum Level {
    HIGH(10);
    Level(int priority) {}
}
```

Trong source, constructor chỉ nhận `int priority`. Nhưng classfile của enum có thêm hai giá trị nội bộ cần thiết cho `java.lang.Enum`:

1. Tên hằng enum (kiểu `String`).
2. Vị trí thứ tự, ordinal (kiểu `int`).

Bởi vậy, Reflection trên mã `javac` có thể thấy chữ ký tương đương `Level(String, int, int)`; hai tham số đầu là compiler-generated synthetic parameters. Đây là lý do `Level.class.getDeclaredConstructor(int.class)` không tìm được constructor mong đợi, còn `getDeclaredConstructor(String.class, int.class, int.class)` có thể tìm được metadata.

**Nhưng không thể dùng Reflection để tự tạo thêm enum constant.** Theo hợp đồng `Constructor.newInstance`, nếu declaring class là enum thì lệnh tạo sẽ ném `IllegalArgumentException`; `setAccessible(true)` không xóa giới hạn ấy. Dùng `Level.HIGH`, `Level.values()` hay `Enum.valueOf(Level.class, "HIGH")` để truy cập các hằng enum hợp lệ đã được khai báo.

Đừng nhầm việc **nhìn thấy constructor signature** với quyền **tạo instance**. Đây là hai phần riêng của hợp đồng Reflection.

## 5. Trường hợp 3: local hoặc anonymous class và giá trị bị capture

Compiler có thể thêm dữ liệu vào constructor để lưu **local variables được capture**. Java chỉ cho phép capture biến cục bộ có giá trị final hoặc *effectively final*; nếu biến bị gán lại làm mất tính effectively final sau khai báo, source sẽ không biên dịch khi lambda/local class đang capture nó.

Ví dụ sau dùng local class trong một static method nên không có enclosing instance kiểu class ngoài; compiler chỉ cần truyền biến `offset` được capture.

Tạo file **`LocalCaptureDemo.java`**:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

public class LocalCaptureDemo {
    public static void main(String[] args) {
        int offset = 8;

        class Local {
            Local(String label) {
                System.out.println(label + offset);
            }
        }

        for (Constructor<?> ctor : Local.class.getDeclaredConstructors()) {
            System.out.println("Constructor: " + ctor);
            for (Parameter p : ctor.getParameters()) {
                System.out.printf(
                        "%s %s implicit=%s synthetic=%s present=%s%n",
                        p.getName(), p.getType(),
                        p.isImplicit(), p.isSynthetic(), p.isNamePresent()
                );
            }
        }
    }
}
```

Chạy:

```bash
javac --release 17 -parameters LocalCaptureDemo.java
java LocalCaptureDemo
```

Kết quả được kiểm chứng với **`javac 21 --release 17 -parameters`**:

```text
Constructor: LocalCaptureDemo$1Local(java.lang.String,int)
label class java.lang.String implicit=false synthetic=false present=true
val$offset int implicit=false synthetic=true present=true
```

Tham số `label` là tham số explicit. `val$offset` được compiler dùng để lưu giá trị của local variable `offset`; trong bản classfile thử nghiệm nó là **synthetic parameter** và được xếp sau `label`.

**Giới hạn cần nhớ:** cách lower local/anonymous class, vị trí tham số capture, tên synthetic và số tham số bổ sung có thể phụ thuộc compiler, phiên bản ngôn ngữ, class được đặt trong static/instance context và biến nào thực sự được dùng. Không được viết thư viện giả định mọi captured parameter đều nằm cuối hoặc đều mang tiền tố `val$`. Hãy kiểm tra metadata thực tế trước khi gọi.

Nếu một local/anonymous class cần enclosing instance và có superclass constructor đặc biệt, cách truyền tham số có thể khác với non-static member class trong mục 3. Không nên lấy quy tắc “tham số đầu luôn là Outer” để áp dụng máy móc cho tất cả local/anonymous classes.

## 6. `-parameters` ảnh hưởng cái gì?

Tùy chọn biên dịch:

```bash
javac --release 17 -parameters ConstructorParametersDemo.java
```

yêu cầu `javac` lưu metadata tên tham số thích hợp trong classfile. API `Parameter.getName()` khi có tên trả tên đã được lưu; `isNamePresent()` cho biết metadata tên có thật hay không.

Nếu biên dịch lại không có `-parameters`, trên bản `javac` đã kiểm tra, các tên ở ví dụ chuyển thành `arg0`, `arg1`... và `isNamePresent()` trở thành `false`. Tuy vậy, **số tham số và loại tham số trong constructor không biến mất**: `Inner` vẫn cần enclosing instance, và enum vẫn có các slot nội bộ. Trong thí nghiệm với `javac 21 --release 17`, cờ implicit/synthetic cho các slot đặc biệt vẫn được phản ánh.

Lưu ý quan trọng:

- `-parameters` **không thêm** các đối số runtime mới; chúng vốn là một phần biểu diễn constructor cần thiết.
- Tên như `arg0` chỉ là tên được tổng hợp khi thiếu metadata; đừng dùng để map tham số nghiệp vụ.
- Đừng dựa vào `isNamePresent()` làm cách kiểm tra rằng một tham số là explicit: synthetic parameter cũng có thể có tên được lưu, như `$enum$name` trong ví dụ.
- Các compiler và build pipelines khác nhau có thể lưu metadata khác nhau; `Parameter.isImplicit()/isSynthetic()` phụ thuộc thông tin classfile đủ để báo cáo chính xác. Nếu metadata không đầy đủ, cần đối chiếu với loại class và constructor signature, không suy luận quá mức từ một cờ `false`.
- Debug information như `LocalVariableTable` **không tương đương** metadata MethodParameters dành cho `Parameter.getName()`.

`javap -v` có thể hữu ích khi nghiên cứu classfile do compiler sinh, nhưng đó là công cụ phân tích; runtime code nên dựa vào API Reflection và hợp đồng của mô hình dữ liệu mình xử lý.

## 7. Vì sao `getDeclaredConstructor(...)` báo `NoSuchMethodException`?

Sai lầm thường gặp:

```java
// Chỉ khai báo một tham số trong source của Inner.
Constructor<?> ctor =
        ConstructorParametersDemo.Inner.class
                .getDeclaredConstructor(String.class);
```

Đây là **mảnh code minh họa lỗi**, dùng class trong chương trình mục 3. Lệnh tìm theo `(String)` không khớp chữ ký thực tế `(ConstructorParametersDemo, String)`, vì vậy `getDeclaredConstructor` ném `NoSuchMethodException`.

Cách tra cứu đúng trong ví dụ:

```java
Constructor<?> ctor =
        ConstructorParametersDemo.Inner.class.getDeclaredConstructor(
                ConstructorParametersDemo.class, String.class
        );
```

Một framework hoặc công cụ không kiểm soát class được nạp nên **đọc danh sách constructor trước**:

```java
for (Constructor<?> ctor : targetClass.getDeclaredConstructors()) {
    System.out.println(ctor);
    for (Parameter parameter : ctor.getParameters()) {
        System.out.printf(
                "  %s, implicit=%s, synthetic=%s%n",
                parameter.getType().getName(),
                parameter.isImplicit(),
                parameter.isSynthetic()
        );
    }
}
```

Đây là **đoạn minh họa nằm trong phương thức có `Class<?> targetClass`**, không phải một chương trình Java độc lập. Sau khi quan sát constructor thực tế, chọn signature và đối số phù hợp; chỉ lọc synthetic/implicit khi đã xác định **hợp đồng khởi tạo** thực sự của loại class tương ứng.

## 8. Gọi `Constructor.newInstance(...)` đúng số lượng, thứ tự và quyền truy cập

`Constructor.newInstance(Object... initargs)` phải nhận đối số cho **tất cả** vị trí tham số runtime phù hợp. Với `Inner` trong ví dụ:

```java
Constructor<?> ctor =
        ConstructorParametersDemo.Inner.class.getDeclaredConstructor(
                ConstructorParametersDemo.class, String.class
        );
ctor.setAccessible(true);

Object obj = ctor.newInstance(new ConstructorParametersDemo(), "ready");
```

Nếu chỉ truyền `"ready"`, Java thiếu enclosing instance: `IllegalArgumentException` là kết quả có thể xảy ra vì số đối số không đúng. Nếu đảo vị trí, receiver/kiểu đối số không tương thích sẽ dẫn tới kiểm tra tham số thất bại. `newInstance` không tự tạo enclosing instance thay cho caller.

Đừng tùy tiện dùng `getDeclaredConstructors()[0]` trong code production: thứ tự các constructor do Reflection trả về không phải một hợp đồng để chọn constructor nghiệp vụ. Nên chỉ định signature, annotation hoặc quy tắc lựa chọn rõ ràng.

Phân biệt thêm:

| Lỗi hoặc giới hạn | Nguyên nhân tiêu biểu |
| --- | --- |
| `NoSuchMethodException` khi tra cứu | Signature `Class<?>...` không khớp đủ tham số, kể cả slot bổ sung |
| `IllegalArgumentException` khi `newInstance` | Sai số đối số, sai kiểu không chuyển đổi được, hoặc cố tạo enum |
| `IllegalAccessException` khi `newInstance` | Constructor/class không accessible và chưa có quyền bỏ qua kiểm tra |
| `InvocationTargetException` | Constructor đã được gọi nhưng code trong constructor ném exception |
| `InstantiationException` | Declaring class là abstract class, không thể tạo instance bình thường |
| `InaccessibleObjectException` khi thử `setAccessible(true)` | Deep reflection bị giới hạn bởi JPMS/module |
| `MalformedParametersException` khi đọc `getParameters()` | Metadata parameter trong classfile không hợp lệ |

**Chú ý về JPMS:** `getDeclaredConstructor` có thể trả metadata của constructor không public; để thực sự gọi nó từ module khác, caller vẫn chịu quy tắc package accessibility và module encapsulation. Việc có synthetic/implicit parameters không thay đổi các quy tắc access ấy.

## 9. Nguyên tắc thiết kế framework xử lý constructor

Nếu viết serializer, dependency-injection container, mapper hoặc plugin loader, nên theo trình tự sau:

1. **Nhận diện loại class:** `Class.isEnum()`, `Class.isMemberClass()`, `Class.isLocalClass()`, `Class.isAnonymousClass()`; kiểm tra `Modifier.isStatic(type.getModifiers())` khi cần.
2. **Lấy metadata constructor thật:** dùng `getDeclaredConstructors()`, `getParameterCount()`, `getParameterTypes()` và `getParameters()`.
3. **Tách tham số framework tạo được và tham số cần người dùng cung cấp:** enclosing instance phải là đúng object bên ngoài; captured state trong local/anonymous class thường không có cách cung cấp ổn định như constructor công khai.
4. **Không dùng chỉ tên tham số:** các tên compiler-generated thiếu tính ổn định; kể cả explicit names cũng phụ thuộc `-parameters`.
5. **Giữ thứ tự thực tế khi invoke:** nếu một constructor có signature `(Outer, String)`, phải truyền đủ hai đối số đúng thứ tự. Việc lọc slot ẩn khỏi UI hiển thị không có nghĩa được bỏ chúng khỏi invocation.
6. **Không cố instantiate enum bằng Reflection:** enum có quy tắc tạo constant riêng; dùng các hằng đã khai báo.
7. **Tôn trọng quyền truy cập:** chỉ dùng `trySetAccessible()/setAccessible` khi có nhu cầu deep reflection hợp pháp và module cho phép. Ưu tiên public factory hoặc API công khai khi khả thi.
8. **Kiểm thử với compiler/build thực tế:** đặc biệt nếu có Kotlin/Scala/bytecode generator hoặc cơ chế compile khác `javac`, cách biểu diễn và metadata có thể khác. Không định nghĩa một quy tắc chung cho mọi ngôn ngữ JVM.

Nếu mục tiêu là sinh đối tượng từ dữ liệu đầu vào theo contract ổn định, nên thiết kế **public factory**, explicit constructor hoặc builder để tránh buộc caller tự dựng enclosing instance/captured state.

## 10. Những nhầm lẫn thường gặp

| Nhận định sai | Sửa lại |
| --- | --- |
| “Constructor Reflection luôn có số tham số bằng source.” | Inner/enum/local class có thể có slot bổ sung trong classfile |
| “Tất cả tham số ẩn đều là synthetic.” | Enclosing instance của member inner class có thể là **implicit**, không synthetic |
| “`Parameter.isNamePresent() == true` thì là tham số user viết.” | Tham số synthetic/implicit cũng có thể có tên trong metadata |
| “Có `-parameters` mới có các tham số bổ sung.” | Tùy chọn này chủ yếu liên quan lưu metadata tên; runtime signature không phụ thuộc nó |
| “Cứ bỏ hết tham số synthetic trước khi gọi `newInstance`.” | `newInstance` cần đối số cho mọi slot trong signature đã chọn |
| “Một inner class luôn có constructor chỉ như mã nguồn.” | Non-static member inner class cần enclosing instance |
| “Static nested class cũng nhận `Outer`.” | Không; static nested class không tự yêu cầu enclosing instance |
| “Tìm thấy enum constructor thì tạo enum mới được.” | `Constructor.newInstance` cấm tạo enum instance |
| “Tên `this$0` hoặc `val$x` luôn giống nhau.” | Đó là chi tiết compiler, không phải public API ổn định |
| “`Constructor.isSynthetic()` cho biết mọi tham số có synthetic không.” | Cần kiểm tra `Parameter.isSynthetic()` trên từng tham số |

## 11. Câu hỏi tự kiểm tra

1. Với `class Outer { class Inner { Inner(int x) {} } }`, nếu `javac` sinh enclosing instance parameter thì `getDeclaredConstructor(...)` cần những `Class<?>` nào, theo thứ tự?
2. Với `static class Nested { Nested(int x) {} }` bên trong `Outer`, có tự động thêm tham số kiểu `Outer` không?
3. Một `Parameter` có `isImplicit() == true` có nhất thiết `isSynthetic() == true` không?
4. Enum có constructor trong source `E(String label)` thì tại sao metadata constructor có thể có thêm hai tham số đầu?
5. Với `-parameters`, vì sao `getName()` hữu ích hơn nhưng vẫn không nên dựa vào tên compiler-generated để định danh logic?
6. Nếu framework lọc hai synthetic parameters của enum khỏi giao diện hiển thị, framework có thể truyền chỉ tham số explicit vào `Constructor.newInstance` để tự tạo enum không?
7. Captured local variable có nhất thiết trở thành parameter được Reflection báo theo cùng một thứ tự ở mọi compiler không?

**Đáp án ngắn:** (1) `Outer.class, int.class`; (2) không; (3) không, là hai phân loại khác nhau; (4) compiler cần tên constant và ordinal; (5) metadata tên phụ thuộc compiler/build, tên bổ sung không ổn định; (6) không, enum không được tạo bằng Reflection; (7) không, phải kiểm tra classfile thực tế.

## 12. Ghi nhớ và tài liệu tham khảo

**Chữ ký constructor qua Reflection mô tả cấu trúc thực tế của executable**, bao gồm những tham số compiler thêm vào để đáp ứng semantics của Java. Khi gặp `NoSuchMethodException` hoặc `IllegalArgumentException` bất ngờ với constructor, hãy kiểm tra declaring class, constructor signature, `Parameter.isImplicit()`, `Parameter.isSynthetic()`, tên có thực sự được lưu hay không, và đầy đủ các đối số runtime cần cung cấp.

Tài liệu chính thức:

- [Java SE 21 — `java.lang.reflect.Parameter`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Parameter.html): ý nghĩa `isImplicit`, `isSynthetic`, `isNamePresent`.
- [Java SE 21 — `java.lang.reflect.Constructor`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Constructor.html): cách `newInstance` xử lý enclosing instance, đối số và enum.
- [Java Language Specification `8.8` — Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8): cấu trúc constructor trong ngôn ngữ Java.
- [Java Language Specification `15.9` — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): enclosing instance và đối số constructor khi tạo object.