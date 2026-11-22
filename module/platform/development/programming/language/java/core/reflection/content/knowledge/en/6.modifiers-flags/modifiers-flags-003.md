# Reflection: đọc các cờ static, final, abstract, synchronized, native và strictfp

Trong Java, các từ khóa `static`, `final`, `abstract`, `synchronized`, `native` và `strictfp` biểu đạt đặc tính của lớp, phương thức hoặc trường dữ liệu. Khi sử dụng Reflection, ta không tìm các từ khóa trong chuỗi source code; ta đọc **modifier bitmask** từ đối tượng `Class`, `Method`, `Field` hoặc `Constructor`, rồi dùng `java.lang.reflect.Modifier` để kiểm tra từng cờ.

Bài này tập trung vào câu hỏi: **modifier đang hiện diện trên phần tử nào, mang ý nghĩa gì và Reflection kiểm tra nó như thế nào?** Cần phân biệt đặc tính được ghi trong metadata với hiệu ứng lúc JVM chạy; đặc biệt, `strictfp` đã thay đổi ý nghĩa trong Java 17+.

## 1. Modifier bitmask trong Reflection hoạt động ra sao?

Những API tiêu biểu:

```java
Class<?> type = SomeClass.class;
int classFlags = type.getModifiers();

java.lang.reflect.Method method =
        type.getDeclaredMethod("someMethod");
int methodFlags = method.getModifiers();

java.lang.reflect.Field field =
        type.getDeclaredField("someField");
int fieldFlags = field.getModifiers();
```

Đây là đoạn minh họa: `SomeClass`, `someMethod` và `someField` phải được khai báo trong chương trình thực tế. Cả ba `getModifiers()` trả về kiểu `int`, nhưng mỗi giá trị thuộc một **ngữ cảnh phần tử** khác nhau.

Mỗi hằng của `Modifier` đại diện cho một bit riêng, ví dụ `Modifier.STATIC`, `Modifier.FINAL`, `Modifier.ABSTRACT`, `Modifier.SYNCHRONIZED`, `Modifier.NATIVE` và `Modifier.STRICT`. Một phần tử có thể mang nhiều bit, kết hợp bằng toán tử OR bit `|`.

```java
int flags = Modifier.PUBLIC | Modifier.STATIC | Modifier.FINAL;

boolean isStatic = Modifier.isStatic(flags);   // true
boolean isFinal = Modifier.isFinal(flags);     // true
boolean isAbstract = Modifier.isAbstract(flags); // false

boolean sameStaticCheck = (flags & Modifier.STATIC) != 0; // true
String labels = Modifier.toString(flags); // "public static final"
```

Đoạn minh họa cần `import java.lang.reflect.Modifier;`. `isXxx(flags)` giúp mã rõ ý nghĩa hơn biểu thức `&`; phép `&` vẫn hữu ích khi cần kết hợp hoặc lọc bitmask.

Điểm quan trọng:

- **`getModifiers()` không trả về một tên modifier duy nhất.** Nó trả về tập cờ mã hóa trong số nguyên.
- **`Modifier.toString(flags)` dùng để trình bày**, không phải kiểm tra quy tắc hợp lệ của khai báo. Nó vẫn có thể in chuỗi từ một bitmask tổng hợp vô lý.
- **Ngữ cảnh quyết định ý nghĩa bit.** Một số bit của class file có ý nghĩa khác nhau ở loại phần tử khác nhau (ví dụ cờ biểu diễn `synchronized` của method khác cờ liên quan lớp). Không đưa modifier của một loại phần tử vào hàm kiểm tra của loại khác rồi suy diễn kết quả.
- Khi cần lọc theo tập modifier phù hợp với loại phần tử, có thể dùng `Modifier.classModifiers()`, `interfaceModifiers()`, `fieldModifiers()`, `methodModifiers()` hoặc `constructorModifiers()`. Đây là **mask cho modifier của ngôn ngữ nguồn**, không phải bộ kiểm tra tự động tất cả quy tắc kết hợp và mọi cờ kỹ thuật của class file.

### API lấy metadata trước khi xét modifier

| Nguồn Reflection | Modifier được đọc | Lưu ý |
| --- | --- | --- |
| `Class.getModifiers()` | Modifier của kiểu (class/interface/nested class) | `static` có ý nghĩa đối với member nested class; top-level class không được khai báo `static` |
| `Method.getModifiers()` | Modifier của một phương thức cụ thể | Dùng để kiểm tra `static`, `final`, `abstract`, `synchronized`, `native`; `strictfp` cần hiểu phiên bản class file |
| `Field.getModifiers()` | Modifier của một trường cụ thể | Thường quan tâm `static`, `final` cùng các cờ khác như `volatile` hoặc `transient` |
| `Constructor.getModifiers()` | Modifier của constructor | Chủ yếu kiểm tra mức truy cập; constructor không thể `static`, `final`, `abstract`, `synchronized` hoặc `native` |

Chọn `getDeclaredMethod(...)`/`getDeclaredField(...)` khi muốn thành viên **khai báo trực tiếp tại lớp**, bao gồm thành viên không public; chọn `getMethod(...)`/`getField(...)` nếu muốn tìm thành viên **public** theo quy tắc kế thừa. Việc có metadata không tự cấp quyền gọi hoặc truy cập thành viên.

## 2. Sáu modifier cần hiểu

| Modifier | Áp dụng thường gặp | Kiểm tra bằng Reflection | Ý nghĩa |
| --- | --- | --- | --- |
| `static` | Field, method, member nested class | `Modifier.isStatic(flags)` | Thành viên gắn với lớp; với nested class, không cần đối tượng của enclosing class |
| `final` | Class, method, field | `Modifier.isFinal(flags)` | Không cho kế thừa class, không cho override method, hoặc không cho gán lại biến field sau khi đã được khởi tạo phù hợp |
| `abstract` | Class, method | `Modifier.isAbstract(flags)` | Class có thể chưa hoàn chỉnh; abstract method khai báo hợp đồng mà không có thân |
| `synchronized` | Method | `Modifier.isSynchronized(flags)` | Khi gọi method, JVM thực hiện đồng bộ monitor trong phạm vi toàn bộ method |
| `native` | Method | `Modifier.isNative(flags)` | Method không có thân mã Java, implementation gắn với native code |
| `strictfp` | Class, interface, method trong mã nguồn lịch sử | `Modifier.isStrict(flags)` | Cờ lịch sử liên quan số thực; từ Java 17 không còn tác dụng điều chỉnh tính toán và không được lưu như trước trong class file mới |

Cột “áp dụng” mô tả phạm vi cú pháp thông dụng; không phải mọi tổ hợp trong bảng đều hợp lệ. Ví dụ, method `abstract` không thể đồng thời là `static`, `final`, `synchronized` hoặc `native`.

## 3. static: thành viên lớp và lớp lồng tĩnh

**`static` field** có một giá trị cấp lớp (cho mỗi `Class` được nạp tương ứng), không phải một bản riêng trên mỗi instance. **`static` method** được gọi theo tên lớp và không có receiver `this`; nó bị **hiding** khi lớp con khai báo method static trùng chữ ký, không override đa hình như instance method.

```java
class Counter {
    static int total;
    static void reset() {
        total = 0;
    }
}
```

Kiểm tra:

```java
java.lang.reflect.Field total =
        Counter.class.getDeclaredField("total");
java.lang.reflect.Method reset =
        Counter.class.getDeclaredMethod("reset");

System.out.println(Modifier.isStatic(total.getModifiers())); // true
System.out.println(Modifier.isStatic(reset.getModifiers())); // true
```

Đây là đoạn minh họa phụ thuộc lớp `Counter` ở trên và khai báo `import java.lang.reflect.Modifier;`; mã gọi cần xử lý hoặc khai báo các checked exception từ `getDeclaredField`/`getDeclaredMethod`.

Nếu class là **member nested class** khai báo `static`:

```java
class Envelope {
    static class Item {
    }
}
```

thì `Modifier.isStatic(Envelope.Item.class.getModifiers())` trả về `true`. Một lớp top-level như `Envelope` không mang modifier `static`. Interface lồng nhau có thể **ngầm định static**, do đó đừng chỉ tìm chữ `static` trong source để suy ra giá trị Reflection. Ngược lại, `static` initializer block không được đại diện bằng đối tượng `Method` thông thường mà ứng dụng tìm với `getDeclaredMethod("<clinit>")`.

Đối với `Method.invoke`, method static không cần instance receiver: có thể truyền `null` cho tham số đối tượng; với instance method, cần receiver phù hợp và có quyền truy cập.

## 4. final: ý nghĩa khác nhau trên class, method và field

**Trên class:** `final class X` không thể có subclass trong Java. **Trên instance method:** `final` cấm lớp con override phương thức đó. **Trên field:** giá trị field không được gán lại sau khi hoàn tất khởi tạo theo quy tắc ngôn ngữ Java.

```java
final class ServiceConfig {
    static final int RETRY_LIMIT = 3;

    final String identity() {
        return "service";
    }
}
```

Với Reflection, cùng một hàm `Modifier.isFinal` kiểm tra cờ `final` ở ba vị trí:

```java
Class<?> t = ServiceConfig.class;
boolean finalClass = Modifier.isFinal(t.getModifiers());

java.lang.reflect.Method m =
        t.getDeclaredMethod("identity");
boolean finalMethod = Modifier.isFinal(m.getModifiers());

java.lang.reflect.Field f =
        t.getDeclaredField("RETRY_LIMIT");
boolean finalField = Modifier.isFinal(f.getModifiers());
```

Đây là đoạn minh họa cần import và xử lý exception tương tự mục 3.

**Không suy ra “đối tượng bất biến” chỉ từ `final`.** Một `final List<String>` không cho gán lại tham chiếu field theo Java thông thường, nhưng nội dung `List` vẫn có thể thay đổi. `static final` không tự động biến mọi field thành compile-time constant; việc có thể inline phụ thuộc loại và biểu thức khởi tạo hằng.

Với Reflection, `final` là dấu hiệu cần tôn trọng trong mô hình dữ liệu; không nên thiết kế logic dựa vào việc tự ý sửa `final` field bằng truy cập phản chiếu. Quy tắc truy cập, inlining, module và JDK hiện đại có thể làm hành vi không khả dụng hoặc khó dự đoán.

## 5. abstract: hợp đồng chưa có thân và kiểu chưa thể new trực tiếp

Một class `abstract` không thể được khởi tạo trực tiếp bằng `new`; nó có thể có cả method abstract lẫn method đã cài đặt. Một method `abstract` khai báo tên, tham số, kiểu trả về, ngoại lệ theo chữ ký, nhưng không cung cấp thân Java.

```java
abstract class Shape {
    abstract double area();

    String category() {
        return "shape";
    }
}
```

`Modifier.isAbstract(Shape.class.getModifiers())` trả về `true`, còn `Modifier.isAbstract(Shape.class.getDeclaredMethod("area").getModifiers())` cũng trả về `true`.

Một số điểm kiểm tra:

- Một class có thể được đánh dấu `abstract` dù không khai báo method abstract nào; `Modifier.isAbstract(classFlags)` và “có method abstract trực tiếp” là hai câu hỏi khác nhau.
- Method abstract không có thân; không thể gọi trực tiếp phương thức abstract khi không có concrete implementation trên receiver. Khi một lớp con cài đặt method, một `Method` tìm từ class cha có thể được invoke trên instance lớp con phù hợp và dispatch đến implementation.
- Một method không thể vừa `abstract` vừa `private`, `static`, `final`, `synchronized`, `native` hoặc `strictfp`.
- Interface vốn là kiểu abstract, nhưng **không phải mọi method của interface đều abstract**: interface có thể có `default`, `static` và `private` methods. Hãy đọc modifier **từng method** thay vì suy từ `isInterface()` của lớp.

## 6. synchronized: chỉ phản ánh khai báo đồng bộ trên method

**Instance `synchronized` method** khóa monitor của receiver (`this`) trong khi method chạy. **Static `synchronized` method** khóa monitor gắn với đối tượng `Class` khai báo phương thức. Đây là hai monitor khác nhau; synchronized chỉ có ý nghĩa nếu các luồng tranh chấp cùng monitor thích hợp.

```java
class BankAccount {
    private int balance;

    public synchronized void deposit(int amount) {
        balance += amount;
    }

    public static synchronized void audit() {
        // Đồng bộ trên BankAccount.class
    }

    public void withdraw(int amount) {
        synchronized (this) {
            balance -= amount;
        }
    }
}
```

Reflection:

```java
java.lang.reflect.Method deposit =
        BankAccount.class.getDeclaredMethod("deposit", int.class);
java.lang.reflect.Method audit =
        BankAccount.class.getDeclaredMethod("audit");
java.lang.reflect.Method withdraw =
        BankAccount.class.getDeclaredMethod("withdraw", int.class);

System.out.println(Modifier.isSynchronized(deposit.getModifiers())); // true
System.out.println(Modifier.isSynchronized(audit.getModifiers()));   // true
System.out.println(Modifier.isSynchronized(withdraw.getModifiers())); // false
```

Đây là đoạn minh họa cần import và xử lý checked exception từ tra cứu. Dòng cuối `false` **không có nghĩa là `withdraw` không đồng bộ gì**: synchronized block trong thân method không khiến method mang cờ `ACC_SYNCHRONIZED`. Reflection modifier chỉ nắm metadata khai báo method, không phân tích mọi lệnh bytecode hay chính sách khóa.

Một method `synchronized` không tự làm mọi thao tác xung quanh thành thread-safe: tính đúng đắn còn phụ thuộc các đường truy cập khác, invariant và việc dùng cùng monitor. Khi `Method.invoke` chạy một synchronized method, lời gọi vẫn chịu semantics đồng bộ của method đó.

## 7. native: phương thức không có phần thân Java

Một method `native` thường là điểm nối tới phần cài đặt ngoài Java, ví dụ qua Java Native Interface (JNI). Nó chỉ có khai báo method, không có thân Java:

```java
class NativeBridge {
    public static native int calculate(int input);
}
```

Sau khi lấy `Method`:

```java
java.lang.reflect.Method method =
        NativeBridge.class.getDeclaredMethod("calculate", int.class);

boolean nativeMethod = Modifier.isNative(method.getModifiers()); // true
boolean staticMethod = Modifier.isStatic(method.getModifiers()); // true
```

Đây là đoạn minh họa cần import và xử lý checked exception từ tra cứu. Chỉ **đọc metadata** của `NativeBridge.calculate` không buộc native implementation phải có sẵn. Nhưng **invoke method native mà chưa liên kết được implementation** có thể dẫn đến `UnsatisfiedLinkError` (khi đi qua Reflection, lỗi từ method có thể được bọc trong `InvocationTargetException`).

`native` không có nghĩa method chắc chắn nhanh hơn Java, an toàn hơn hay tự được phép truy cập mọi tài nguyên. Nó chỉ mô tả hình thức implementation. Các giới hạn tải thư viện, liên kết native và cấu hình JDK vẫn cần được xử lý độc lập.

## 8. strictfp: di sản cũ và thay đổi quan trọng từ Java 17

Trước Java 17, `strictfp` giúp buộc các phép tính `float`/`double` trong phạm vi nhất định tuân theo ngữ nghĩa floating-point strict. Java 17 khôi phục ngữ nghĩa **always-strict** theo JEP 306: phép toán floating-point có cùng quy tắc strict bất kể từ khóa `strictfp` có xuất hiện hay không.

Hệ quả khi đọc modifier bằng Reflection:

1. `Modifier.STRICT` và `Modifier.isStrict(int)` vẫn là API giải mã **bit**. Nếu tự xây bitmask `Modifier.PUBLIC | Modifier.STRICT`, `isStrict` sẽ trả về `true`, vì bit có mặt.
2. **Điều đó không có nghĩa method được biên dịch bởi JDK 17+ sẽ mang cờ strict.** Theo JVMS 17, bit `ACC_STRICT` chỉ được diễn giải là `strictfp` trong class file có major version từ **46 đến 60**. Với class file major **61+** (Java 17+), bit đó không còn ý nghĩa `ACC_STRICT`; mã biên dịch mới không cần ghi nó.
3. Vì thế, dù trong mã nguồn Java 17+ viết `strictfp`, `Modifier.isStrict(method.getModifiers())` thường trả về `false`. **Không thể dùng giá trị `false` để chứng minh rằng source không có từ khóa `strictfp`.**
4. `strictfp` là từ khóa lỗi thời, compiler hiện đại có thể cảnh báo; không nên thêm vào mã Java mới để “tăng độ chính xác” của phép tính số thực. Khi đọc class file cũ, luôn xét phiên bản class file trước khi suy diễn cờ strict.

Ví dụ minh họa **mã nguồn lịch sử**, không yêu cầu chạy:

```java
strictfp class OldCalculation {
    strictfp double half(double input) {
        return input / 2.0;
    }
}
```

Trên Java 17+, từ khóa trên không làm thay đổi kết quả tính `input / 2.0`. Dùng Reflection thuần chỉ thấy metadata được lưu trong class file; nếu muốn biết chính xác **từ khóa từng xuất hiện trong source**, phải phân tích source hoặc metadata chuyên dụng phù hợp, không suy ngược chỉ từ `getModifiers()`.

## 9. Chương trình Java 17+ hoàn chỉnh: kiểm tra sáu cờ

Tạo tệp `ModifierFlagsDemo.java`:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class ModifierFlagsDemo {
    static abstract class Task {
        abstract int calculate(int number);

        final String kind() {
            return "task";
        }
    }

    static final class IncrementTask extends Task {
        public static final int STEP = 1;

        @Override
        int calculate(int number) {
            return number + STEP;
        }

        public synchronized int run(int number) {
            return calculate(number);
        }

        // Chỉ khai báo native: ví dụ không bao giờ gọi method này.
        public static native void nativeEntry();
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<?> taskClass = Task.class;
        Class<?> implClass = IncrementTask.class;

        Method abstractMethod =
                taskClass.getDeclaredMethod("calculate", int.class);
        Method finalMethod = taskClass.getDeclaredMethod("kind");
        Method synchronizedMethod =
                implClass.getDeclaredMethod("run", int.class);
        Method nativeMethod =
                implClass.getDeclaredMethod("nativeEntry");
        Field stepField = implClass.getDeclaredField("STEP");

        System.out.println("Task abstract: "
                + Modifier.isAbstract(taskClass.getModifiers()));
        System.out.println("Task.calculate abstract: "
                + Modifier.isAbstract(abstractMethod.getModifiers()));
        System.out.println("Task.kind final: "
                + Modifier.isFinal(finalMethod.getModifiers()));
        System.out.println("IncrementTask final: "
                + Modifier.isFinal(implClass.getModifiers()));
        System.out.println("IncrementTask nested static: "
                + Modifier.isStatic(implClass.getModifiers()));

        int stepFlags = stepField.getModifiers();
        System.out.println("STEP static final: "
                + (Modifier.isStatic(stepFlags) && Modifier.isFinal(stepFlags)));

        int runFlags = synchronizedMethod.getModifiers();
        System.out.println("run synchronized: "
                + Modifier.isSynchronized(runFlags));
        System.out.println("run static: "
                + Modifier.isStatic(runFlags));
        System.out.println("run modifiers: "
                + Modifier.toString(runFlags));

        int nativeFlags = nativeMethod.getModifiers();
        System.out.println("nativeEntry native: "
                + Modifier.isNative(nativeFlags));
        System.out.println("nativeEntry static: "
                + Modifier.isStatic(nativeFlags));

        // Chỉ giải mã bitmask minh họa, không phải cờ trong class file mới.
        int legacyStrictMask = Modifier.PUBLIC | Modifier.STRICT;
        System.out.println("legacy strict bit: "
                + Modifier.isStrict(legacyStrictMask));

        Object result = synchronizedMethod.invoke(new IncrementTask(), 4);
        System.out.println("run(4): " + result);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac ModifierFlagsDemo.java
java ModifierFlagsDemo
```

Kết quả stdout:

```text
Task abstract: true
Task.calculate abstract: true
Task.kind final: true
IncrementTask final: true
IncrementTask nested static: true
STEP static final: true
run synchronized: true
run static: false
run modifiers: public synchronized
nativeEntry native: true
nativeEntry static: true
legacy strict bit: true
run(4): 5
```

Giải thích:

- `Task` mang cờ `abstract`; method `calculate` cũng mang cờ riêng `abstract`. Ngược lại, method `kind` mang cờ `final` chứ không `abstract`.
- `IncrementTask` vừa là lớp lồng `static` vừa là lớp `final`; cờ trên class phản ánh đặc tính class, không tự động suy ra mọi method đều `static` hoặc `final`.
- `STEP` có cả cờ `static` và `final`. Hãy kiểm tra **cả hai bit**, vì không phải `static` luôn đồng nghĩa `final`.
- `run` là instance method `public synchronized`, nên `isSynchronized` là `true` còn `isStatic` là `false`. `Modifier.toString` trình bày các cờ của **method này** theo thứ tự chuẩn.
- `nativeEntry` được khai báo `static native`; chương trình **chỉ lấy metadata**, không gọi native method nên không cần thư viện JNI để chạy ví dụ.
- `legacyStrictMask` do chương trình chủ động tạo từ `Modifier.STRICT` để minh họa cách kiểm tra bit. Nó **không** đại diện cho một method được biên dịch từ `strictfp` bằng JDK 17+.
- `Method.invoke` trên `run` tuân theo cơ chế instance method và monitor; kết quả phép tính là `4 + 1 = 5`, được Reflection trả về dưới dạng `Object` chứa `Integer`.

## 10. Thiết kế bộ lọc Reflection theo modifier

Giả sử chỉ muốn liệt kê những **method public, static, không native** được khai báo trực tiếp trong một class. Có thể lọc như sau:

```java
for (java.lang.reflect.Method method : SomeClass.class.getDeclaredMethods()) {
    int flags = method.getModifiers();
    if (Modifier.isPublic(flags)
            && Modifier.isStatic(flags)
            && !Modifier.isNative(flags)
            && !method.isSynthetic()
            && !method.isBridge()) {
        System.out.println(method.getName());
    }
}
```

Đây là đoạn minh họa, cần một `SomeClass` thực tế và `import java.lang.reflect.Modifier;`. Nó xét **method tự khai báo** nhờ `getDeclaredMethods()`; muốn xét cả method public kế thừa cần cân nhắc `getMethods()`. Không giả định thứ tự mảng method được JVM trả về; sắp xếp nếu công cụ cần đầu ra ổn định. Các bộ lọc `isSynthetic()`/`isBridge()` là tùy nhu cầu công cụ, bởi compiler có thể sinh method phụ trợ.

Thứ tự ra quyết định:

1. **Chọn đúng đối tượng `Class<?>`**: kiểu khai báo hoặc kiểu runtime theo mục tiêu kiểm tra.
2. **Chọn phạm vi khám phá**: `getDeclared*` đối với khai báo riêng của lớp hoặc `get*` để tìm thành viên public theo quy tắc API.
3. **Đọc `getModifiers()`** từ chính class, method hoặc field đang xét; không sử dụng một cờ của class như chứng cứ cho mọi thành viên.
4. **Giải mã từng cờ bằng `Modifier.isXxx(flags)`**, kết hợp điều kiện khi cần (ví dụ `static && final`). Dùng `Modifier.toString` để hiển thị, không lấy đó làm bộ xác thực toàn diện.
5. **Diễn giải theo ngữ nghĩa Java**: `final` không bảo đảm deep immutability; `synchronized` flag không nhìn thấy synchronized block; `native` metadata không chứng minh thư viện native đã sẵn sàng; `strictfp` trong class file mới không thể suy như class file cũ.

## 11. Các lỗi thường gặp

| Ngộ nhận | Sự thật/cách xử lý |
| --- | --- |
| Một số nguyên từ `getModifiers()` biểu thị đúng một từ khóa | Đó là nhiều bit có thể cùng bật; kiểm tra `Modifier.isXxx` hoặc `&` |
| `Modifier.isFinal(SomeClass.class.getModifiers())` cho biết mọi field đều final | Nó chỉ kiểm tra **class**; hãy kiểm tra modifier của từng `Field` |
| `final` field làm đối tượng được tham chiếu bất biến | Nó giới hạn việc gán lại field; trạng thái đối tượng được tham chiếu có thể vẫn thay đổi |
| `static` method được override như instance method | Static method được chọn theo quy tắc hiding; không có dynamic dispatch override theo receiver như instance method |
| Không có cờ `synchronized` nghĩa là không dùng khóa | Method vẫn có thể chứa synchronized block hoặc cơ chế khóa khác |
| `Modifier.isNative(flags)` là chứng cứ native library đã được nạp | Chỉ chứng minh method mang cờ native; khả năng liên kết/chạy là chuyện khác |
| Java 17+ `isStrict() == false` nghĩa là source không có `strictfp` | Java 17+ luôn dùng ngữ nghĩa FP strict và không cần lưu ACC_STRICT như class file cũ |
| `getMethods()` và `getDeclaredMethods()` giống nhau | Một API thiên về public và kế thừa, API kia chỉ khai báo trực tiếp, bất kể access |
| Có metadata private nghĩa là được tùy ý gọi/đọc | Quyền truy cập và giới hạn module vẫn phải được tuân thủ |
| `Modifier.toString(flags)` bảo đảm các cờ hợp lệ với phần tử | Hàm chỉ render bitmask; ngữ cảnh và tổ hợp hợp lệ vẫn phải được xét riêng |

## 12. Câu hỏi tự kiểm tra

1. **Một method `public static synchronized` có thể có cả `isStatic` và `isSynchronized` bằng `true` không?** Có. Method static synchronized đồng bộ trên monitor của đối tượng `Class`.
2. **Một class `final` có thể chứa method `abstract` không?** Không. Class `final` không thể kế thừa để hoàn thiện abstract method; `final` và `abstract` không thể kết hợp trên class.
3. **`Modifier.isSynchronized` phát hiện được `synchronized(this)` trong thân method thường không?** Không. Nó chỉ đọc flag khai báo method.
4. **Chưa load thư viện JNI, có thể đọc `getDeclaredMethod("nativeEntry")` và `isNative` không?** Có, miễn class và metadata liên quan đọc được; ví dụ không gọi method native.
5. **Tại sao `Modifier.isStrict` không đáng tin để phát hiện từ khóa trong mã nguồn Java 17+?** Vì mã FP luôn strict và `ACC_STRICT` chỉ được định nghĩa cho class-file major 46–60, nên mã class file mới không phải giữ bit đó.
6. **Một field `static final List<?>` có chắc list bất biến không?** Không. Không gán lại tham chiếu field không đồng nghĩa chặn thay đổi nội dung list.

**Ghi nhớ:** `Modifier` giúp giải mã **cờ metadata của đúng phần tử**. Muốn hiểu tác động, luôn xét loại phần tử, phạm vi Reflection và phiên bản Java/class file; bản thân cờ không thay thế phân tích ngữ nghĩa Java hoặc hành vi runtime.